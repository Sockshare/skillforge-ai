#!/usr/bin/env python3
"""SkillForge AI — Zero-Dependency HTTP Server & REST API."""

import argparse
import mimetypes
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from mcp_server import process_mcp_jsonrpc
from skillforge import __version__
from skillforge.compiler import (
    build_zip_bundle,
    compile_skill,
    evaluate_skill_deterministically,
    parse_blueprint_or_preset,
)
from skillforge.llm_bridge import (
    DEFAULT_TRANSFORMATION_DOC,
    get_ollama_status,
    translate_webapp_with_llm,
)
from skillforge.presets import list_presets

ROOT_DIR = Path(__file__).resolve().parent


class SkillForgeRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for SkillForge AI Studio & REST API."""

    server_version = f"SkillForgeAI/{__version__}"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/api/health":
            ollama = get_ollama_status()
            self._send_json(
                {
                    "status": "ok",
                    "service": "skillforge-ai",
                    "version": __version__,
                    "presets_available": len(list_presets()),
                    "mcp_protocol_version": "2024-11-05",
                    "ollama_connected": ollama["connected"],
                    "ollama_models": ollama["models"],
                }
            )
            return

        if route == "/api/llm/status":
            ollama = get_ollama_status()
            self._send_json(
                {
                    "ollama": ollama,
                    "default_transformation_doc": DEFAULT_TRANSFORMATION_DOC,
                    "supported_providers": [
                        {"id": "ollama", "label": "Local Ollama (http://127.0.0.1:11434)"},
                        {"id": "openai", "label": "OpenAI / OpenRouter Compatible API"},
                        {"id": "gemini", "label": "Google Gemini Cloud API"},
                        {"id": "deterministic_ast", "label": "Deterministic AST Route & Schema Introspector (Offline)"},
                    ],
                }
            )
            return

        if route == "/api/presets":
            self._send_json({"presets": list_presets()})
            return

        if route in ("/", "/index.html"):
            target_file = ROOT_DIR / "index.html"
        elif route.startswith("/static/"):
            rel = route.lstrip("/")
            target_file = (ROOT_DIR / rel).resolve()
            if not str(target_file).startswith(str((ROOT_DIR / "static").resolve())):
                self._send_json({"error": "Forbidden path"}, status=HTTPStatus.FORBIDDEN)
                return
        else:
            self._send_json({"error": f"Not found: {route}"}, status=HTTPStatus.NOT_FOUND)
            return

        if not target_file.is_file():
            self._send_json({"error": "Asset not found"}, status=HTTPStatus.NOT_FOUND)
            return

        content = target_file.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(target_file))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            body = self._read_json_body()
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"Invalid JSON payload: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        if route == "/api/llm/translate":
            try:
                webapp_source = body.get("webapp_source") or body.get("blueprint") or ""
                transformation_doc = body.get("transformation_doc") or DEFAULT_TRANSFORMATION_DOC
                llm_config = body.get("llm_config") or {"provider": "ollama", "model": "llama3.2:3b"}
                llm_res = translate_webapp_with_llm(webapp_source, transformation_doc, llm_config)
                spec_override = llm_res.get("spec_override") or {}
                merged_payload = dict(body)
                merged_payload["custom_override"] = True
                for k in ("name", "title", "category", "description", "guardrails", "rules", "sample_input"):
                    if spec_override.get(k):
                        merged_payload[k] = spec_override[k]
                compiled = compile_skill(merged_payload)
                compiled["llm_translation"] = {
                    "provider": llm_res["provider"],
                    "model": llm_res["model"],
                    "endpoint": llm_res["endpoint"],
                    "used_transformation_doc": True,
                }
                self._send_json(compiled)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"LLM translation failed: {exc}"}, status=HTTPStatus.BAD_GATEWAY)
            return

        if route == "/api/compile":
            compiled = compile_skill(body)
            self._send_json(compiled)
            return

        if route == "/api/mcp/rpc":
            rpc_req = body.get("rpc") if isinstance(body.get("rpc"), dict) else body
            skill_ctx = body.get("skill_context") if isinstance(body.get("skill_context"), dict) else None
            rpc_resp = process_mcp_jsonrpc(rpc_req, skill_context=skill_ctx)
            self._send_json(rpc_resp)
            return

        if route == "/api/verify-determinism":
            spec = parse_blueprint_or_preset(body)
            input_payload = body.get("sample_input") or body.get("payload") or spec["sample_input"]
            runs = [evaluate_skill_deterministically(spec, input_payload) for _ in range(3)]
            hashes = [r["determinism_sha256"] for r in runs]
            compiled = compile_skill(body)
            self._send_json(
                {
                    "skill_id": spec["id"],
                    "title": spec["title"],
                    "deterministic": len(set(hashes)) == 1,
                    "run_1_sha256": hashes[0],
                    "run_2_sha256": hashes[1],
                    "run_3_sha256": hashes[2],
                    "evaluation": runs[0],
                    "gates": compiled["gates"],
                    "all_gates_passed": compiled["all_gates_passed"],
                }
            )
            return

        if route == "/api/bundle.zip":
            compiled = compile_skill(body)
            zip_bytes = build_zip_bundle(compiled)
            slug = compiled["spec"]["name"]
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{slug}-skill-bundle.zip"')
            self.send_header("Content-Length", str(len(zip_bytes)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(zip_bytes)
            return

        self._send_json({"error": f"Unknown endpoint: {route}"}, status=HTTPStatus.NOT_FOUND)


def create_server(host: str = "127.0.0.1", port: int = 8091) -> ThreadingHTTPServer:
    """Instantiate a ThreadingHTTPServer bound to host:port."""
    return ThreadingHTTPServer((host, port), SkillForgeRequestHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description="SkillForge AI Web Studio Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8091, help="TCP port (default: 8091)")
    args = parser.parse_args()

    httpd = create_server(args.host, args.port)
    print(f"SkillForge AI Studio listening on http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
