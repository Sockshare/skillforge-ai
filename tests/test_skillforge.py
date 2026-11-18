#!/usr/bin/env python3
"""Comprehensive Unit, Integration, MCP, HTTP API & Zero-Proprietary-Content Test Suite."""

import base64
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cli import write_compiled_artifacts  # noqa: E402
from mcp_server import process_mcp_jsonrpc  # noqa: E402
from server import create_server  # noqa: E402
from skillforge.compiler import (  # noqa: E402
    build_zip_bundle,
    compile_skill,
    evaluate_skill_deterministically,
    parse_blueprint_or_preset,
)
from skillforge.presets import PRESETS, list_presets  # noqa: E402

# Base64-encoded forbidden terms so that not even this test file contains literal proprietary strings
FORBIDDEN_B64_TERMS = [
    "Z29vZ2xlMw==",          # g...3
    "cGlwZXI=",              # p...r
    "Y2l0Yw==",              # c...c
    "Ym9yZw==",              # b...g
    "Ym9x",                  # b...q
    "Ymx1emU=",              # b...e
    "Z2FucGF0aQ==",          # g...i
    "cnBjc3A=",              # r...p
    "a2V5c3RvcmU=",          # k...e
    "YnVnYW5pemVy",          # b...r
    "ZzNkb2M=",              # g...c
    "bWRiLw==",              # m.../
    "bG9hcw==",              # l...s
    "emFuemliYXI=",          # z...r
    "c3Bhbm5lcg==",          # s...r
    "YmxvYnN0b3Jl",          # b...e
    "dHdvc3luYw==",          # t...c
    "MnN5bmM=",              # 2...c
    "Zm9ydGlmeQ==",          # f...y
    "bWFudGlz",              # m...s
    "dHJpY29yZGVy",          # t...r
    "cGVlcGxl",              # p...e
    "cGVvcGxldmlldw==",      # p...w
    "Z2NsbQ==",              # g...m
    "b3Jlbw==",              # o...o
    "Y29uY29yZA==",          # c...d
    "YWNjb3Jk",              # a...d
    "c25lYWt5cGF3",          # s...w
    "YWJwcmFtYW5paw==",      # a...k
    "bW9ycmlzZXR0ZQ==",      # m...e
    "anVsaWFu",              # j...n
]


class TestSkillForgeCompilerAndPresets(unittest.TestCase):
    def test_six_builtin_presets_present(self) -> None:
        presets = list_presets()
        self.assertEqual(len(presets), 6)
        expected_ids = {
            "aws-iam-least-privilege-auditor",
            "k8s-zero-trust-network-verifier",
            "soc2-continuous-control-monitor",
            "gdpr-pii-dataflow-lineage-scanner",
            "openapi-idor-authz-triage-engine",
            "finops-cloud-cost-anomaly-detector",
        }
        self.assertEqual({p["id"] for p in presets}, expected_ids)

    def test_compile_all_six_presets_and_five_gates(self) -> None:
        for preset_id in PRESETS:
            with self.subTest(preset_id=preset_id):
                compiled = compile_skill({"preset_id": preset_id})
                self.assertTrue(compiled["all_gates_passed"])
                self.assertEqual(len(compiled["gates"]), 5)
                self.assertEqual(len(compiled["stages"]), 4)
                for expected_file in (
                    "SKILL.md",
                    "mcp_server.py",
                    "scripts/engine.py",
                    "references/schema.json",
                    "tests/test_skill.py",
                ):
                    self.assertIn(expected_file, compiled["artifacts"])
                    self.assertGreater(len(compiled["artifacts"][expected_file]), 50)

    def test_three_run_cryptographic_determinism_all_presets(self) -> None:
        for preset_id in PRESETS:
            with self.subTest(preset_id=preset_id):
                spec = parse_blueprint_or_preset({"preset_id": preset_id})
                r1 = evaluate_skill_deterministically(spec, spec["sample_input"])
                r2 = evaluate_skill_deterministically(spec, spec["sample_input"])
                r3 = evaluate_skill_deterministically(spec, spec["sample_input"])
                self.assertEqual(r1["determinism_sha256"], r2["determinism_sha256"])
                self.assertEqual(r2["determinism_sha256"], r3["determinism_sha256"])
                self.assertEqual(len(r1["determinism_sha256"]), 64)
                self.assertGreaterEqual(r1["findings_count"], 1)

    def test_custom_openapi_blueprint_compilation(self) -> None:
        custom_openapi = {
            "openapi": "3.1.0",
            "info": {"title": "Payments Ledger Service", "version": "2.1.0"},
            "paths": {
                "/v1/ledgers/{ledger_id}": {"get": {}},
                "/v1/settlements/{settlement_id}": {"post": {}},
            },
        }
        compiled = compile_skill(
            {
                "name": "payments-ledger-openapi-guard",
                "category": "AppSec OpenAPI",
                "blueprint": json.dumps(custom_openapi),
            }
        )
        self.assertTrue(compiled["all_gates_passed"])
        self.assertEqual(compiled["spec"]["id"], "payments-ledger-openapi-guard")
        self.assertTrue(compiled["determinism"]["deterministic"])

    def test_zip_bundle_generation_and_standalone_execution(self) -> None:
        compiled = compile_skill({"preset_id": "aws-iam-least-privilege-auditor"})
        zip_bytes = build_zip_bundle(compiled)
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()
            self.assertIn("aws-iam-least-privilege-auditor/SKILL.md", names)
            self.assertIn("aws-iam-least-privilege-auditor/scripts/engine.py", names)

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = write_compiled_artifacts(compiled, Path(tmpdir))
            proc = subprocess.run(
                [sys.executable, str(skill_dir / "scripts/engine.py"), "--verify-determinism"],
                cwd=str(skill_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            out_json = json.loads(proc.stdout)
            self.assertTrue(out_json["deterministic"])
            self.assertEqual(out_json["runs"], 3)


class TestMcpServerAndHttpApi(unittest.TestCase):
    def test_mcp_jsonrpc_methods(self) -> None:
        init_res = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(init_res["result"]["protocolVersion"], "2024-11-05")

        list_res = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {t["name"] for t in list_res["result"]["tools"]}
        self.assertIn("list_skill_presets", tool_names)
        self.assertIn("compile_agent_skill", tool_names)
        self.assertIn("aws_iam_least_privilege_auditor", tool_names)

        call_res = process_mcp_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "k8s_zero_trust_network_verifier", "arguments": {}},
            }
        )
        self.assertFalse(call_res["result"]["isError"])
        self.assertEqual(len(call_res["result"]["meta"]["determinism_sha256"]), 64)

    def test_http_server_endpoints(self) -> None:
        httpd = create_server("127.0.0.1", 0)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(f"{base_url}/api/health") as resp:
                self.assertEqual(resp.status, 200)
                health = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")
                self.assertEqual(health["presets_available"], 6)

            with urllib.request.urlopen(f"{base_url}/") as resp:
                html = resp.read().decode("utf-8")
                self.assertIn("SkillForge AI", html)

            req = urllib.request.Request(
                f"{base_url}/api/compile",
                data=json.dumps({"preset_id": "soc2-continuous-control-monitor"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                compiled = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(compiled["all_gates_passed"])

            det_req = urllib.request.Request(
                f"{base_url}/api/verify-determinism",
                data=json.dumps({"preset_id": "gdpr-pii-dataflow-lineage-scanner"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(det_req) as resp:
                det_data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(det_data["deterministic"])
                self.assertEqual(det_data["run_1_sha256"], det_data["run_3_sha256"])

            with urllib.request.urlopen(f"{base_url}/api/mcp/configs") as resp:
                cfgs = json.loads(resp.read().decode("utf-8"))
                self.assertIn("claude_desktop_config", cfgs)
                self.assertIn("cursor_mcp_config", cfgs)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_pc_application_scan_and_multi_tool_extraction(self) -> None:
        from skillforge.workspace import scan_pc_application_folder

        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "inventory-billing-app"
            app_dir.mkdir()
            (app_dir / "server.py").write_text(
                'from fastapi import FastAPI\napp = FastAPI()\n\n'
                '@app.get("/api/invoices")\ndef list_invoices(customer_id: str):\n    return []\n\n'
                '@app.post("/api/invoices/pay")\ndef pay_invoice(invoice_id: str, amount: float):\n    return {"paid": True}\n',
                encoding="utf-8",
            )
            scan_res = scan_pc_application_folder(str(app_dir))
            self.assertEqual(scan_res["app_name"], "inventory-billing-app")
            self.assertGreaterEqual(len(scan_res["routes_discovered"]), 2)
            self.assertGreaterEqual(len(scan_res["functions_extracted"]), 2)
            # Should have suite_runner + 2 HTTP route tools + 2 extracted function tools = 5 tools
            self.assertGreaterEqual(len(scan_res["tools_discovered"]), 5)

    def test_multi_skill_mcp_hub_and_multi_llm_profiles(self) -> None:
        from skillforge.llm_bridge import delete_llm_profile, list_llm_profiles, upsert_llm_profile
        from skillforge.workspace import delete_workspace_skill, list_workspace_skills, save_skill_to_workspace

        prof = upsert_llm_profile(
            {
                "id": "test-local-vllm",
                "name": "Local vLLM Test Profile",
                "provider": "custom_openai",
                "base_url": "http://127.0.0.1:8000/v1",
                "model": "qwen2.5-coder-7b",
            }
        )
        self.assertEqual(prof["id"], "test-local-vllm")
        self.assertTrue(any(p["id"] == "test-local-vllm" for p in list_llm_profiles()))
        delete_llm_profile("test-local-vllm")

        # Compile and install two distinct multi-tool skills into the MCP workspace
        s1 = compile_skill(
            {
                "name": "order-tracker-app-skill",
                "custom_override": True,
                "blueprint": '@app.get("/api/orders")\ndef get_orders(): pass\n@app.post("/api/orders/cancel")\ndef cancel_order(): pass\n',
            }
        )
        s2 = compile_skill(
            {
                "name": "warehouse-audit-app-skill",
                "custom_override": True,
                "blueprint": '@app.get("/api/stock")\ndef check_stock(): pass\n@app.post("/api/stock/reconcile")\ndef reconcile_stock(): pass\n',
            }
        )
        save_skill_to_workspace(s1)
        save_skill_to_workspace(s2)
        try:
            installed = {w["name"] for w in list_workspace_skills()}
            self.assertIn("order-tracker-app-skill", installed)
            self.assertIn("warehouse-audit-app-skill", installed)

            list_res = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
            tool_names = {t["name"] for t in list_res["result"]["tools"]}
            self.assertIn("order_tracker_app_skill__get_api_orders", tool_names)
            self.assertIn("order_tracker_app_skill__post_api_orders_cancel", tool_names)
            self.assertIn("warehouse_audit_app_skill__get_api_stock", tool_names)
            self.assertIn("warehouse_audit_app_skill__fn_reconcile_stock", tool_names)

            res_list = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 11, "method": "resources/list"})
            uris = {r["uri"] for r in res_list["result"]["resources"]}
            self.assertIn("skill://order-tracker-app-skill/SKILL.md", uris)
            self.assertIn("skill://warehouse-audit-app-skill/SKILL.md", uris)
        finally:
            delete_workspace_skill("order-tracker-app-skill")
            delete_workspace_skill("warehouse-audit-app-skill")


class TestZeroProprietaryContent(unittest.TestCase):
    def test_zero_proprietary_terms_across_entire_repository(self) -> None:
        decoded_forbidden = [base64.b64decode(b).decode("utf-8").lower() for b in FORBIDDEN_B64_TERMS]
        text_extensions = {".py", ".md", ".html", ".css", ".js", ".json", ".sh", ".txt", ""}
        checked_files = 0

        for path in ROOT_DIR.rglob("*"):
            if not path.is_file():
                continue
            if any(part in path.parts for part in (".git", "__pycache__", "skills_workspace")):
                continue
            if path.name == "server.log":
                continue
            if path.suffix.lower() not in text_extensions:
                continue

            content = path.read_text(encoding="utf-8", errors="ignore").lower()
            checked_files += 1
            for term in decoded_forbidden:
                self.assertNotIn(
                    term,
                    content,
                    msg=f"Forbidden proprietary term found in {path.relative_to(ROOT_DIR)}",
                )

        self.assertGreaterEqual(checked_files, 10)


if __name__ == "__main__":
    unittest.main()
