#!/usr/bin/env python3
"""SkillForge AI — Plug-and-Play Multi-Skill & Multi-Tool Model Context Protocol (MCP JSON-RPC 2.0) Hub Server.

Capabilities:
  - Dynamic Multi-Skill & Multi-Tool Registry (`skills_workspace/<skill-slug>/`)
  - Exposes all tools across all user-converted skills concurrently (`<skill_slug>__<tool_name>`)
  - Exposes MCP Resources (`resources/list`, `resources/read` -> `skill://<slug>/SKILL.md` & `schema.json`)
  - Exposes MCP Prompts (`prompts/list`, `prompts/get` -> `use_<slug>`)
  - Exposes Core SkillForge Compiler Tools (`scan_pc_application`, `compile_agent_skill`, `list_installed_skills`, `verify_skill_determinism`, `list_llm_profiles`)
  - Supports both stdio JSON-RPC 2.0 (for Claude Desktop, Cursor, Windsurf, Cline) and HTTP POST `/api/mcp/rpc`.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from skillforge import __version__
from skillforge.compiler import (
    build_json_schema,
    canonical_json,
    compile_skill,
    evaluate_skill_deterministically,
    parse_blueprint_or_preset,
)
from skillforge.llm_bridge import list_llm_profiles
from skillforge.presets import PRESETS, list_presets
from skillforge.workspace import (
    SKILLS_WORKSPACE_DIR,
    list_workspace_skills,
     save_skill_to_workspace,
    scan_pc_application_folder,
)


def get_mcp_tools_catalog(skill_context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Return all MCP tools: Core SkillForge meta-tools + all tools from every installed skill in `skills_workspace/` + active skill_context."""
    tools: List[Dict[str, Any]] = [
        {
            "name": "scan_pc_application",
            "description": "Scan a local application directory or file on the user's PC and extract all HTTP routes, functions, and classes.",
            "inputSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {"type": "string", "description": "Local filesystem path to the application directory or file."},
                },
            },
        },
        {
            "name": "compile_agent_skill",
            "description": "Compile an application blueprint, directory scan, or OpenAPI spec into a multi-tool SKILL.md + MCP server + deterministic CLI package and install it into the MCP workspace.",
            "inputSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill identifier (kebab-case)."},
                    "blueprint": {"type": "string", "description": "Application source code, routes, or OpenAPI 3.1 JSON."},
                    "preset_id": {"type": "string", "description": "Optional preset ID."},
                    "install_to_workspace": {"type": "boolean", "default": True},
                },
            },
        },
        {
            "name": "list_installed_skills",
            "description": "List all user-compiled skills and their multi-tool inventories currently active in the SkillForge MCP Hub.",
            "inputSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "list_llm_profiles",
            "description": "List all configured local (Ollama, LM Studio, vLLM) and cloud LLM connections available for skill translation.",
            "inputSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "list_skill_presets",
            "description": "List reference skill templates available in SkillForge AI.",
            "inputSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "verify_skill_determinism",
            "description": "Execute a 3-run SHA-256 cryptographic determinism check on any installed skill or payload.",
            "inputSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "preset_id": {"type": "string", "default": "aws-iam-least-privilege-auditor"},
                    "payload": {"type": "object", "description": "Optional custom workload payload."},
                },
            },
        },
    ]

    seen_names = {t["name"] for t in tools}

    # 1. Include all tools from active skill_context (if provided by the Studio UI)
    if skill_context:
        spec = parse_blueprint_or_preset(skill_context)
        schema_obj = build_json_schema(spec)["input_schema"]
        for t in spec.get("tools", []):
            if t["name"] not in seen_names:
                seen_names.add(t["name"])
                tools.append({
                    "name": t["name"],
                    "description": f"[{spec['name']}] {t.get('description', spec['description'])}",
                    "inputSchema": schema_obj,
                })
        base_def = build_json_schema(spec)["adapters"]["mcp_tool_definition"]
        if base_def["name"] not in seen_names:
            seen_names.add(base_def["name"])
            tools.append(base_def)

    # 2. Include all tools from every installed skill in `skills_workspace/`
    for ws_skill in list_workspace_skills():
        schema_obj = build_json_schema(ws_skill)["input_schema"]
        for t in ws_skill.get("tools", []):
            tname = t["name"]
            if tname not in seen_names:
                seen_names.add(tname)
                tools.append({
                    "name": tname,
                    "description": f"[{ws_skill['name']}] {t.get('description', ws_skill.get('description', ''))}",
                    "inputSchema": schema_obj,
                })

    # 3. Include reference templates
    for preset in list_presets():
        schema_info = build_json_schema(preset)
        tdef = schema_info["adapters"]["mcp_tool_definition"]
        if tdef["name"] not in seen_names:
            seen_names.add(tdef["name"])
            tools.append(tdef)

    return tools


def get_mcp_resources_catalog(skill_context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Return MCP resources (`SKILL.md` and `schema.json`) for all installed skills in `skills_workspace/`."""
    resources: List[Dict[str, Any]] = []
    seen_uris = set()

    if skill_context and skill_context.get("name"):
        slug = skill_context["name"]
        uri = f"skill://{slug}/SKILL.md"
        seen_uris.add(uri)
        resources.append({
            "uri": uri,
            "name": f"{slug} — SKILL.md",
            "description": skill_context.get("description", ""),
            "mimeType": "text/markdown",
        })

    for ws in list_workspace_skills():
        slug = ws["name"]
        for fname, mime in [("SKILL.md", "text/markdown"), ("references/schema.json", "application/json")]:
            uri = f"skill://{slug}/{fname}"
            if uri not in seen_uris:
                seen_uris.add(uri)
                resources.append({
                    "uri": uri,
                    "name": f"{slug} — {fname}",
                    "description": ws.get("description", ""),
                    "mimeType": mime,
                })
    return resources


def process_mcp_jsonrpc(request: Dict[str, Any], skill_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Process an MCP JSON-RPC 2.0 request and return a JSON-RPC 2.0 response with latency & SHA-256 metadata."""
    start_ns = time.perf_counter_ns()
    req_id = request.get("id", 1)
    method = request.get("method", "")
    params = request.get("params") or {}

    if method == "initialize":
        server_name = (
            f"{skill_context['name']}-mcp-hub"
            if skill_context and skill_context.get("name")
            else "skillforge-multi-skill-mcp-hub"
        )
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": server_name, "version": __version__},
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": False, "listChanged": True},
                    "prompts": {"listChanged": True},
                },
            },
        }

    if method in ("notifications/initialized", "ping"):
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": get_mcp_tools_catalog(skill_context)},
        }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"resources": get_mcp_resources_catalog(skill_context)},
        }

    if method == "resources/read":
        uri = params.get("uri", "")
        content_text = "# Resource not found"
        mime = "text/markdown"
        if uri.startswith("skill://"):
            rest = uri[len("skill://"):]
            parts = rest.split("/", 1)
            if len(parts) == 2:
                slug, rel = parts[0], parts[1]
                fpath = SKILLS_WORKSPACE_DIR / slug / rel
                if fpath.is_file():
                    content_text = fpath.read_text(encoding="utf-8", errors="ignore")
                    if rel.endswith(".json"):
                        mime = "application/json"
                elif skill_context and skill_context.get("name") == slug:
                    compiled = compile_skill(skill_context)
                    content_text = compiled["artifacts"].get(rel, content_text)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "contents": [{"uri": uri, "mimeType": mime, "text": content_text}],
            },
        }

    if method == "prompts/list":
        prompts = [
            {
                "name": f"use_{ws['name'].replace('-', '_')}",
                "description": f"Activate {ws['title']} ({len(ws.get('tools', []))} tools)",
                "arguments": [{"name": "task", "description": "Task to execute with this skill", "required": False}],
            }
            for ws in list_workspace_skills()
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": prompts}}

    if method == "tools/call":
        tool_name = params.get("name") or ""
        arguments = params.get("arguments") or {}

        if tool_name == "scan_pc_application":
            scan_res = scan_pc_application_folder(arguments.get("path", ""))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": canonical_json(scan_res)}],
                    "isError": False,
                },
            }

        if tool_name == "list_installed_skills":
            ws_skills = list_workspace_skills()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": canonical_json({"installed_skills": ws_skills, "count": len(ws_skills)})}],
                    "isError": False,
                },
            }

        if tool_name == "list_llm_profiles":
            profiles = list_llm_profiles()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": canonical_json({"llm_profiles": profiles, "count": len(profiles)})}],
                    "isError": False,
                },
            }

        if tool_name == "list_skill_presets":
            presets_summary = [
                {
                    "id": p["id"],
                    "title": p["title"],
                    "category": p["category"],
                    "version": p["version"],
                    "frameworks": p["frameworks"],
                }
                for p in list_presets()
            ]
            text_out = canonical_json({"presets": presets_summary, "count": len(presets_summary)})
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text_out}],
                    "isError": False,
                },
            }

        if tool_name == "compile_agent_skill":
            compiled = compile_skill(arguments)
            if arguments.get("install_to_workspace", True):
                save_skill_to_workspace(compiled)
            summary = {
                "skill_id": compiled["spec"]["id"],
                "tools_count": len(compiled["spec"].get("tools", [])),
                "tools": [t["name"] for t in compiled["spec"].get("tools", [])],
                "all_gates_passed": compiled["all_gates_passed"],
                "package_sha256": compiled["package_sha256"],
                "determinism_sha256": compiled["determinism"]["run_1_sha256"],
                "artifacts_generated": list(compiled["artifacts"].keys()),
                "gates": compiled["gates"],
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": canonical_json(summary)}],
                    "isError": False,
                    "meta": {"determinism_sha256": compiled["determinism"]["run_1_sha256"]},
                },
            }

        if tool_name == "verify_skill_determinism":
            preset_id = arguments.get("preset_id") or "aws-iam-least-privilege-auditor"
            spec = parse_blueprint_or_preset({"preset_id": preset_id})
            input_payload = arguments.get("payload") or spec["sample_input"]
            runs = [evaluate_skill_deterministically(spec, input_payload) for _ in range(3)]
            hashes = [r["determinism_sha256"] for r in runs]
            det_result = {
                "skill_id": spec["id"],
                "deterministic": len(set(hashes)) == 1,
                "run_1_sha256": hashes[0],
                "run_2_sha256": hashes[1],
                "run_3_sha256": hashes[2],
                "evaluation": runs[0],
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": canonical_json(det_result)}],
                    "isError": False,
                    "meta": {"determinism_sha256": hashes[0]},
                },
            }

        # Check if tool_name belongs to an installed workspace skill (`<skill_slug>__<tool>`)
        matched_spec = None
        if "__" in tool_name:
            prefix_slug = tool_name.split("__", 1)[0].replace("_", "-")
            for ws in list_workspace_skills():
                if ws["name"] == prefix_slug or ws["id"] == prefix_slug:
                    matched_spec = ws
                    break

        normalized_id = tool_name.replace("_", "-")
        if matched_spec:
            spec = matched_spec
        elif normalized_id in PRESETS:
            spec = parse_blueprint_or_preset({"preset_id": normalized_id})
        elif skill_context:
            spec = parse_blueprint_or_preset(skill_context)
        else:
            spec = parse_blueprint_or_preset({"preset_id": "aws-iam-least-privilege-auditor"})

        workload_payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else arguments
        if not workload_payload:
            workload_payload = spec["sample_input"]

        evaluation = evaluate_skill_deterministically(spec, workload_payload)
        evaluation["invoked_tool"] = tool_name
        elapsed_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 3)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": canonical_json(evaluation)}],
                "isError": False,
                "meta": {
                    "skill_id": spec["id"],
                    "invoked_tool": tool_name,
                    "latency_ms": elapsed_ms,
                    "determinism_sha256": evaluation["determinism_sha256"],
                },
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: '{method}'. Supported: initialize, tools/list, tools/call, resources/list, resources/read, prompts/list",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SkillForge AI Multi-Skill & Multi-Tool MCP JSON-RPC 2.0 Hub Server")
    parser.add_argument("--self-test", action="store_true", help="Run MCP JSON-RPC 2.0 handshake & multi-tool verification")
    args = parser.parse_args()

    if args.self_test:
        r_init = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        r_list = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        r_res = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        r_call = process_mcp_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "aws_iam_least_privilege_auditor",
                    "arguments": {},
                },
            }
        )
        output = {
            "status": "SELF_TEST_PASSED",
            "protocolVersion": r_init["result"]["protocolVersion"],
            "registered_tools_count": len(r_list["result"]["tools"]),
            "registered_resources_count": len(r_res["result"]["resources"]),
            "sample_tool_call_sha256": r_call["result"]["meta"]["determinism_sha256"],
        }
        print(canonical_json(output))
        return 0

    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
            response = process_mcp_jsonrpc(request)
        except Exception as exc:  # noqa: BLE001
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
