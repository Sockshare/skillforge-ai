#!/usr/bin/env python3
"""SkillForge AI — Zero-Dependency HTTP Server & Multi-Skill / Multi-LLM REST API."""

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

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
    delete_llm_profile,
    execute_skill_with_llm_test,
    get_ollama_status,
    list_llm_profiles,
    translate_webapp_with_llm,
    upsert_llm_profile,
)
from skillforge.presets import list_presets
from skillforge.workspace import (
    browse_pc_directory,
    delete_workspace_skill,
    get_mcp_client_configs,
    list_workspace_skills,
    save_skill_to_workspace,
    scan_pc_application_folder,
)

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        qs = parse_qs(parsed.query)

        if route == "/api/health":
            ollama = get_ollama_status()
            ws_skills = list_workspace_skills()
            self._send_json(
                {
                    "status": "ok",
                    "service": "skillforge-ai",
                    "version": __version__,
                    "presets_available": len(list_presets()),
                    "installed_workspace_skills": len(ws_skills),
                    "mcp_protocol_version": "2024-11-05",
                    "ollama_connected": ollama["connected"],
                    "ollama_models": ollama["models"],
                }
            )
            return

        if route == "/api/fs/browse":
            raw_path = qs.get("path", [None])[0]
            self._send_json(browse_pc_directory(raw_path))
            return

        if route == "/api/llm/status":
            ollama = get_ollama_status()
            self._send_json(
                {
                    "ollama": ollama,
                    "profiles": list_llm_profiles(),
                    "default_transformation_doc": DEFAULT_TRANSFORMATION_DOC,
                }
            )
            return

        if route == "/api/llm/profiles":
            self._send_json({"profiles": list_llm_profiles()})
            return

        if route == "/api/workspace/skills":
            skills = list_workspace_skills()
            total_tools = sum(len(s.get("tools", [])) for s in skills)
            self._send_json(
                {
                    "skills": skills,
                    "skills_count": len(skills),
                    "total_tools_count": total_tools,
                }
            )
            return

        if route == "/api/mcp/configs":
            port = self.server.server_port if hasattr(self.server, "server_port") else 8108
            self._send_json(get_mcp_client_configs(port))
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

        if route == "/api/fs/load-sample-app":
            try:
                sample_dir = ROOT_DIR / "examples" / "taskpulse-webapp"
                sibling_dir = ROOT_DIR.parent / "skill-test-webapp"
                chosen_dir = sample_dir if sample_dir.exists() else sibling_dir
                scan_result = scan_pc_application_folder(str(chosen_dir))
                scan_result["app_name"] = "TaskPulse"
                scan_result["skill_slug"] = "taskpulse-webapp-skill"
                scan_result["default_target_url"] = "http://127.0.0.1:8110"
                self._send_json(scan_result)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"Failed to load sample application: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        if route == "/api/fs/scan-app":
            try:
                app_path = body.get("path") or ""
                scan_result = scan_pc_application_folder(app_path)
                self._send_json(scan_result)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"Failed to scan PC application: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        if route == "/api/llm/profiles":
            prof = upsert_llm_profile(body)
            self._send_json({"profile": prof, "profiles": list_llm_profiles()})
            return

        if route == "/api/llm/translate":
            try:
                webapp_source = body.get("webapp_source") or body.get("blueprint") or ""
                transformation_doc = body.get("transformation_doc") or DEFAULT_TRANSFORMATION_DOC
                llm_config = body.get("llm_config") or {"provider": "ollama", "model": "llama3.2:3b"}
                app_hint = body.get("name") or "custom-webapp-skill"
                llm_res = translate_webapp_with_llm(webapp_source, transformation_doc, llm_config, app_hint_name=app_hint)
                spec_override = llm_res.get("spec_override") or {}
                merged_payload = dict(body)
                merged_payload["custom_override"] = True
                for k in ("name", "title", "category", "description", "guardrails", "rules", "tools", "sample_input"):
                    if spec_override.get(k):
                        merged_payload[k] = spec_override[k]
                compiled = compile_skill(merged_payload)
                if body.get("install_to_workspace", True):
                    save_skill_to_workspace(compiled)
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
            if body.get("install_to_workspace", True):
                save_skill_to_workspace(compiled)
            self._send_json(compiled)
            return

        if route == "/api/workspace/skills":
            compiled = compile_skill(body)
            manifest = save_skill_to_workspace(compiled)
            self._send_json({"installed": manifest, "skills": list_workspace_skills()})
            return

        if route == "/api/workspace/delete":
            removed = delete_workspace_skill(body.get("id") or body.get("name") or "")
            self._send_json({"deleted": removed, "skills": list_workspace_skills()})
            return

        if route == "/api/mcp/rpc":
            rpc_req = body.get("rpc") if isinstance(body.get("rpc"), dict) else body
            skill_ctx = body.get("skill_context") if isinstance(body.get("skill_context"), dict) else None
            rpc_resp = process_mcp_jsonrpc(rpc_req, skill_context=skill_ctx)
            self._send_json(rpc_resp)
            return

        if route == "/api/skill/test-with-llm":
            try:
                skill_slug = body.get("skill_slug") or ""
                user_prompt = body.get("prompt") or "Check the status and list tasks"
                llm_config = body.get("llm_config") or {"provider": "ollama", "model": "llama3.2:3b"}
                target_app_url = body.get("target_app_url") or "http://127.0.0.1:8110"
                result = execute_skill_with_llm_test(
                    skill_slug=skill_slug,
                    user_prompt=user_prompt,
                    llm_config=llm_config,
                    target_app_url=target_app_url,
                )
                self._send_json(result)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"Skill test execution failed: {exc}"}, status=HTTPStatus.BAD_GATEWAY)
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

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        qs = parse_qs(parsed.query)
        if route == "/api/llm/profiles":
            pid = qs.get("id", [""])[0]
            removed = delete_llm_profile(pid)
            self._send_json({"deleted": removed, "profiles": list_llm_profiles()})
            return
        if route == "/api/workspace/skills":
            sid = qs.get("id", [""])[0]
            removed = delete_workspace_skill(sid)
            self._send_json({"deleted": removed, "skills": list_workspace_skills()})
            return
        self._send_json({"error": f"Unknown DELETE endpoint: {route}"}, status=HTTPStatus.NOT_FOUND)


def create_server(host: str = "127.0.0.1", port: int = 8108) -> ThreadingHTTPServer:
    """Create and return a configured ThreadingHTTPServer instance."""
    return ThreadingHTTPServer((host, port), SkillForgeRequestHandler)


def run_server(host: str = "127.0.0.1", port: int = 8108) -> None:
    server = create_server(host, port)
    print(f"SkillForge AI Studio listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="SkillForge AI Web Server & REST API")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8108, help="Bind port (default: 8108)")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
