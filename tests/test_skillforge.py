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

    def test_dual_route_profiles_and_live_taskpulse_skill_execution(self) -> None:
        import importlib.util
        from http.server import ThreadingHTTPServer
        from skillforge.llm_bridge import execute_skill_with_llm_test, list_llm_profiles
        from skillforge.workspace import delete_workspace_skill, save_skill_to_workspace, scan_pc_application_folder

        # 1. Verify Local Onboard Ollama is always #1 default route + Cloud API profiles exist
        profiles = list_llm_profiles()
        self.assertGreaterEqual(len(profiles), 4)
        self.assertEqual(profiles[0]["group"], "local_onboard")
        self.assertEqual(profiles[0]["provider"], "ollama")
        profile_ids = {p["id"] for p in profiles}
        self.assertIn("cloud-gemini", profile_ids)
        self.assertIn("cloud-openai", profile_ids)
        self.assertIn("cloud-anthropic", profile_ids)

        # 2. Spin up bundled TaskPulse sample web app on an ephemeral port
        tp_dir = ROOT_DIR / "examples" / "taskpulse-webapp"
        spec_mod = importlib.util.spec_from_file_location("taskpulse_srv", tp_dir / "server.py")
        assert spec_mod and spec_mod.loader
        tp_module = importlib.util.module_from_spec(spec_mod)
        spec_mod.loader.exec_module(tp_module)

        tp_httpd = ThreadingHTTPServer(("127.0.0.1", 0), tp_module.TaskPulseHandler)
        tp_port = tp_httpd.server_address[1]
        tp_thread = threading.Thread(target=tp_httpd.serve_forever, daemon=True)
        tp_thread.start()

        try:
            # 3. Scan & compile TaskPulse into an installed MCP Skill
            scan_data = scan_pc_application_folder(str(tp_dir))
            compiled = compile_skill(
                {
                    "name": "taskpulse-unit-test-skill",
                    "custom_override": True,
                    "blueprint": scan_data["combined_source"],
                }
            )
            save_skill_to_workspace(compiled)

            # 4. Execute budget calculation & task creation via Skill <-> LLM bridge against live TaskPulse
            budget_res = execute_skill_with_llm_test(
                skill_slug="taskpulse-unit-test-skill",
                user_prompt="Calculate the project budget for 20 hours at $100/hr with 10% tax",
                llm_config={"provider": "ollama", "model": "llama3.2:3b"},
                target_app_url=f"http://127.0.0.1:{tp_port}",
            )
            self.assertTrue(budget_res["ok"])
            self.assertEqual(budget_res["http_path"], "/api/calculate-budget")
            self.assertEqual(budget_res["tool_output"]["grand_total_usd"], 2200.0)
            self.assertTrue(budget_res["skill_md_loaded"])
        finally:
            delete_workspace_skill("taskpulse-unit-test-skill")
            tp_httpd.shutdown()
            tp_httpd.server_close()


class TestEnterpriseSkillBuilderAndGuardrailsLab(unittest.TestCase):
    def test_hundred_skill_progressive_router_and_context_savings(self) -> None:
        from skillforge.enterprise_kit import get_hundred_skills_catalog, simulate_progressive_skill_router

        catalog = get_hundred_skills_catalog()
        self.assertEqual(len(catalog), 100)

        routed = simulate_progressive_skill_router(
            "Nightly billing invoice batch stalled with ORA-00060 row lock and 504 correlation timeout; check logs and draft Jira RCA",
            top_k=3,
            use_subagent_isolation=True,
        )
        self.assertEqual(routed["total_skills_in_registry"], 100)
        self.assertEqual(len(routed["selected_skills"]), 3)
        tc = routed["token_comparison"]
        self.assertTrue(tc["naive_overflows_200k"])
        self.assertGreater(tc["context_reduction_pct"], 95.0)
        self.assertLess(tc["routed_progressive_total_tokens"], 10000)

    def test_pretooluse_guardrails_sql_bash_secret_and_hitl(self) -> None:
        from skillforge.enterprise_kit import evaluate_pre_tool_use_hook

        allow_sql = evaluate_pre_tool_use_hook(
            "OracleSQL",
            {"sql": "SELECT sid, serial#, blocking_session FROM v$session WHERE blocking_session IS NOT NULL"},
        )
        self.assertTrue(allow_sql["allowed"])
        self.assertEqual(allow_sql["exit_code"], 0)

        block_sql = evaluate_pre_tool_use_hook("OracleSQL", {"sql": "DELETE FROM invoice_ledger WHERE status = 'STUCK'"})
        self.assertFalse(block_sql["allowed"])
        self.assertEqual(block_sql["exit_code"], 2)
        self.assertEqual(block_sql["decision"], "BLOCK")

        block_rm = evaluate_pre_tool_use_hook("Bash", {"command": "rm -rf /var/log/billing"})
        self.assertFalse(block_rm["allowed"])
        self.assertEqual(block_rm["exit_code"], 2)

        block_env = evaluate_pre_tool_use_hook("Read", {"file_path": "/srv/app/.env"})
        self.assertFalse(block_env["allowed"])
        self.assertEqual(block_env["exit_code"], 2)

        hitl_gate = evaluate_pre_tool_use_hook("Bash", {"command": "systemctl restart billing-worker"}, hitl_approved=False)
        self.assertFalse(hitl_gate["allowed"])
        self.assertEqual(hitl_gate["decision"], "REQUIRE_HITL")

        hitl_ok = evaluate_pre_tool_use_hook("Bash", {"command": "systemctl restart billing-worker"}, hitl_approved=True)
        self.assertTrue(hitl_ok["allowed"])
        self.assertEqual(hitl_ok["decision"], "ALLOW_WITH_HITL")

    def test_skill_creator_benchmark_and_trigger_optimizer(self) -> None:
        from skillforge.enterprise_kit import optimize_trigger_description, run_skill_creator_eval_suite

        b1 = run_skill_creator_eval_suite("billing-ops-diagnostics")
        b2 = run_skill_creator_eval_suite("billing-ops-diagnostics")
        self.assertEqual(b1["benchmark_sha256"], b2["benchmark_sha256"])
        self.assertEqual(b1["benchmark"]["with_skill"]["mean_pass_rate_pct"], 100.0)
        self.assertGreater(b1["benchmark"]["delta"]["token_reduction_pct"], 70.0)

        opt = optimize_trigger_description("Helps debug billing issues and database problems.")
        self.assertEqual(opt["split_summary"]["total_queries"], 20)
        self.assertEqual(opt["held_out_test_accuracy_pct"], 100.0)
        self.assertIn("Do not use for", opt["best_description"])

    def test_http_and_mcp_kit_endpoints_and_starter_zip_self_tests(self) -> None:
        httpd = create_server("127.0.0.1", 0)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(f"{base}/") as r:
                ui_html = r.read().decode("utf-8")
                self.assertIn("enterprise-skill-builder-lab", ui_html)
                self.assertIn("Runtime Framework Guardrails Lab", ui_html)
                self.assertIn("100-Skill Context Router", ui_html)

            with urllib.request.urlopen(f"{base}/api/kit/overview") as r:
                ov = json.loads(r.read().decode("utf-8"))
                self.assertEqual(len(ov["topics"]), 6)
                self.assertEqual(ov["hundred_skills_count"], 100)
                self.assertEqual(len(ov["starter_kit_files"]), 14)

            ops_req = urllib.request.Request(
                f"{base}/api/fs/load-billing-ops-app",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(ops_req) as r:
                ops_scan = json.loads(r.read().decode("utf-8"))
                self.assertEqual(ops_scan["app_name"], "BillingOps Diagnostics")
                self.assertGreaterEqual(len(ops_scan["routes_discovered"]), 5)

            zip_req = urllib.request.Request(
                f"{base}/api/kit/starter-bundle.zip",
                data=json.dumps({"project_name": "telecom-billing-ops"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(zip_req) as r:
                zbytes = r.read()

            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(io.BytesIO(zbytes), "r") as zf:
                    zf.extractall(tmpdir)
                kit_root = Path(tmpdir) / "telecom-billing-ops-agent-kit"
                self.assertTrue((kit_root / "CLAUDE.md").is_file())
                self.assertTrue((kit_root / "AGENTS.md").is_file())
                self.assertTrue((kit_root / ".claude/settings.json").is_file())
                self.assertTrue((kit_root / "docs/COMPLETE_ARCHITECTURE_GUIDE.md").is_file())
                proc = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                    cwd=str(kit_root),
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertIn("OK", proc.stderr + proc.stdout)

            # Verify new MCP JSON-RPC 2.0 tools
            mcp_guard = process_mcp_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "tools/call",
                    "params": {
                        "name": "evaluate_pretooluse_guardrail",
                        "arguments": {"tool_name": "OracleSQL", "tool_input": {"sql": "DROP TABLE invoices"}},
                    },
                }
            )
            parsed_guard = json.loads(mcp_guard["result"]["content"][0]["text"])
            self.assertFalse(parsed_guard["allowed"])
            self.assertEqual(parsed_guard["exit_code"], 2)
        finally:
            httpd.shutdown()
            httpd.server_close()


class TestSkillCreatorOneToOneAndOrchestrator(unittest.TestCase):
    def test_ollama_discovery_headless_decoupler_and_real_skill_creator_loop(self) -> None:
        import shutil
        from skillforge.llm_bridge import get_ollama_status
        from skillforge.skill_creator_studio import (
            EVAL_WORKSPACES_DIR,
            build_standalone_headless_skill,
            interview_skill_intent,
            package_standalone_skill_archive,
            run_real_skill_creator_evals,
            submit_human_feedback_and_iterate,
            update_skill_frontmatter_description,
        )
        from skillforge.workspace import delete_workspace_skill

        ollama = get_ollama_status()
        self.assertIn("connected", ollama)
        self.assertIn("models", ollama)
        self.assertIn("model_details", ollama)

        webapp_code = (ROOT_DIR / "examples" / "billing-ops-webapp" / "server.py").read_text(encoding="utf-8")
        interview = interview_skill_intent(
            goal="Audit billing database locks and service ACL scope in production",
            app_source=webapp_code,
            trigger_hints="ORA-00060 locks, production scope check",
        )
        self.assertGreaterEqual(len(interview["clarifying_questions"]), 2)
        self.assertGreaterEqual(len(interview["proposed_evals"]), 2)

        test_slug = "unit-headless-billing-verifier"
        try:
            built = build_standalone_headless_skill(
                {
                    "name": test_slug,
                    "title": "Unit Headless Billing Verifier",
                    "webapp_source": webapp_code,
                    "stage_role": "discovery",
                }
            )
            man = built["manifest"]
            self.assertEqual(man["mode"], "standalone_headless_cli")
            self.assertTrue(man["determinism"]["deterministic"])
            self.assertGreaterEqual(len(man["extracted_webapp_functions"]), 2)
            self.assertIn("BUILD.bazel", built["artifacts"])
            self.assertIn("INSTALL.md", built["artifacts"])
            self.assertIn("evals/evals.json", built["artifacts"])

            # Run real subprocess evals (Iteration 1: with_skill vs without_skill)
            ev1 = run_real_skill_creator_evals(test_slug)
            self.assertEqual(ev1["iteration"], 1)
            self.assertEqual(ev1["benchmark"]["with_skill"]["pass_rate"]["mean"], 1.0)
            self.assertTrue(Path(ev1["viewer_html_path"]).is_file())
            self.assertTrue((Path(ev1["workspace_dir"]) / "benchmark.json").is_file())

            # Submit human feedback.json -> snapshot skill -> refine SKILL.md -> run Iteration 2 against old_skill
            ev2 = submit_human_feedback_and_iterate(
                skill_slug=test_slug,
                iteration=1,
                reviews=[{"run_id": "eval-0-with_skill", "feedback": "Include concise executive summary bullets at top."}],
            )
            self.assertEqual(ev2["iteration"], 2)
            self.assertEqual(ev2["benchmark"]["baseline"]["label"], "old_skill")
            self.assertTrue((Path(ev1["workspace_dir"]) / "feedback.json").is_file())

            upd = update_skill_frontmatter_description(
                test_slug,
                "Updated pushy trigger description. Use when auditing production billing locks. Do not use for CSS.",
            )
            self.assertIn("Do not use for CSS", upd["updated_description"])

            skill_zip = package_standalone_skill_archive(test_slug)
            with zipfile.ZipFile(io.BytesIO(skill_zip), "r") as zf:
                znames = zf.namelist()
                self.assertIn(f"{test_slug}/SKILL.md", znames)
                self.assertIn(f"{test_slug}/BUILD.bazel", znames)
        finally:
            delete_workspace_skill(test_slug)
            ws_eval = EVAL_WORKSPACES_DIR / f"{test_slug}-workspace"
            if ws_eval.exists():
                shutil.rmtree(ws_eval)

    def test_multi_skill_sequential_orchestrator_and_two_run_determinism(self) -> None:
        import shutil
        from skillforge.orchestrator_builder import (
            PIPELINE_RUNS_DIR,
            REFERENCE_COMPLIANCE_STAGES,
            build_orchestrator_suite_zip,
            execute_orchestrator_pipeline,
            provision_compliance_reference_suite,
        )
        from skillforge.workspace import SKILLS_WORKSPACE_DIR, delete_workspace_skill

        try:
            prov = provision_compliance_reference_suite()
            self.assertEqual(prov["total_skills_provisioned"], 6)
            orch_slug = prov["orchestrator"]["name"]
            self.assertEqual(orch_slug, "compliance-master-orchestrator")

            # 1. Execute full sequential pipeline & verify Stage 1 -> Stage 2..5 handoff + Master Report
            full_run = execute_orchestrator_pipeline(
                pipeline_slug=orch_slug,
                target_app="PaymentsCore",
                component_ids="10401,10402",
                run_mode="full_workflow",
            )
            self.assertTrue(full_run["ok"])
            self.assertEqual(len(full_run["stages_executed"]), 5)
            self.assertGreaterEqual(full_run["verified_handoff_count"], 3)
            self.assertEqual(len(full_run["master_report"]["dataset_sha256"]), 64)
            self.assertIn("mermaid", full_run["master_markdown_preview"])

            # 2. Execute Two-Run Independent SHA-256 Determinism Proof (Run A == Run B)
            two_run = execute_orchestrator_pipeline(
                pipeline_slug=orch_slug,
                target_app="PaymentsCore",
                component_ids="10401,10402",
                run_mode="two_run_determinism",
            )
            self.assertTrue(two_run["deterministic"])
            self.assertEqual(two_run["verdict"], "CRYPTOGRAPHICALLY_IDENTICAL_PASS")
            self.assertEqual(two_run["dataset_sha256_run_a"], two_run["dataset_sha256_run_b"])
            self.assertEqual(two_run["report_sha256_run_a"], two_run["report_sha256_run_b"])
            self.assertEqual(len(two_run["stage_hash_comparisons"]), 5)
            self.assertTrue(all(s["identical"] for s in two_run["stage_hash_comparisons"]))

            # 3. Verify Unified 1-Command CLI Launcher (`./compliance-master-cli list`)
            launcher_path = SKILLS_WORKSPACE_DIR / orch_slug / "compliance-master-cli"
            cli_proc = subprocess.run(
                [sys.executable, str(launcher_path), "list"],
                cwd=str(SKILLS_WORKSPACE_DIR / orch_slug),
                capture_output=True,
                text=True,
                check=True,
            )
            listed = json.loads(cli_proc.stdout)
            self.assertEqual(len(listed["stages"]), 5)

            # 4. Verify downloadable suite .zip includes orchestrator + all 5 member skills
            suite_zip = build_orchestrator_suite_zip(orch_slug)
            with zipfile.ZipFile(io.BytesIO(suite_zip), "r") as zf:
                znames = zf.namelist()
                self.assertTrue(any("compliance-master-orchestrator/SKILL.md" in n for n in znames))
                self.assertTrue(any("service-acl-scope-discovery/SKILL.md" in n for n in znames))
                self.assertTrue(any("vuln-sla-and-7gate-validator/SKILL.md" in n for n in znames))
        finally:
            delete_workspace_skill("compliance-master-orchestrator")
            for st in REFERENCE_COMPLIANCE_STAGES:
                delete_workspace_skill(st["name"])
            if PIPELINE_RUNS_DIR.exists():
                shutil.rmtree(PIPELINE_RUNS_DIR)


class TestZeroProprietaryContent(unittest.TestCase):
    def test_zero_proprietary_terms_across_entire_repository(self) -> None:
        decoded_forbidden = [base64.b64decode(b).decode("utf-8").lower() for b in FORBIDDEN_B64_TERMS]
        text_extensions = {".py", ".md", ".html", ".css", ".js", ".json", ".sh", ".txt", ""}
        checked_files = 0

        for path in ROOT_DIR.rglob("*"):
            if not path.is_file():
                continue
            if any(part in path.parts for part in (".git", "__pycache__", "skills_workspace", "eval_workspaces", "pipeline_runs")):
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

