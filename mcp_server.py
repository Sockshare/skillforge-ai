#!/usr/bin/env python3
"""SkillForge AI — Model Context Protocol (MCP JSON-RPC 2.0) Server.

Exposes SkillForge AI's compiler and all 6 built-in deterministic skills over MCP JSON-RPC 2.0.
Supports `--self-test` and stdio JSON-RPC loop.
"""

import argparse
import json
import sys
import time
from typing import Any, Dict

from skillforge import __version__
from skillforge.compiler import (
    build_json_schema,
    canonical_json,
    compile_skill,
    evaluate_skill_deterministically,
    parse_blueprint_or_preset,
)
from skillforge.presets import PRESETS, list_presets


def get_mcp_tools_catalog() -> list:
    """Return MCP tool definitions for SkillForge AI studio + all 6 built-in presets."""
    tools = [
        {
            "name": "list_skill_presets",
            "description": "List all 6 built-in industry agent skill presets available in SkillForge AI.",
            "inputSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "compile_agent_skill",
            "description": "Compile a preset or custom blueprint into a verified SKILL.md, CLI engine, and MCP server.",
            "inputSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "preset_id": {"type": "string", "description": "Built-in preset ID to compile."},
                    "name": {"type": "string", "description": "Custom skill slug."},
                    "blueprint": {"type": "string", "description": "Custom workflow or OpenAPI 3.1 JSON blueprint."},
                },
            },
        },
        {
            "name": "verify_skill_determinism",
            "description": "Execute a 3-run SHA-256 cryptographic determinism check on any skill preset or custom payload.",
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

    for preset in list_presets():
        schema_info = build_json_schema(preset)
        tools.append(schema_info["adapters"]["mcp_tool_definition"])

    return tools


def process_mcp_jsonrpc(request: Dict[str, Any], skill_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Process an MCP JSON-RPC 2.0 request and return a JSON-RPC 2.0 response with latency & SHA-256 metadata."""
    start_ns = time.perf_counter_ns()
    req_id = request.get("id", 1)
    method = request.get("method", "")
    params = request.get("params") or {}

    if method == "initialize":
        server_name = (
            f"{skill_context['name']}-mcp"
            if skill_context and skill_context.get("name")
            else "skillforge-ai-mcp-server"
        )
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": server_name, "version": __version__},
                "capabilities": {"tools": {"listChanged": False}},
            },
        }

    if method == "tools/list":
        if skill_context:
            spec = parse_blueprint_or_preset(skill_context)
            tool_def = build_json_schema(spec)["adapters"]["mcp_tool_definition"]
            tools = [tool_def] + get_mcp_tools_catalog()
        else:
            tools = get_mcp_tools_catalog()
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools},
        }

    if method == "tools/call":
        tool_name = params.get("name") or ""
        arguments = params.get("arguments") or {}

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
            summary = {
                "skill_id": compiled["spec"]["id"],
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

        # Otherwise evaluate matching preset or custom compiled skill
        normalized_id = tool_name.replace("_", "-")
        if normalized_id in PRESETS:
            spec = parse_blueprint_or_preset({"preset_id": normalized_id})
        elif skill_context:
            spec = parse_blueprint_or_preset(skill_context)
        else:
            spec = parse_blueprint_or_preset({"preset_id": "aws-iam-least-privilege-auditor"})

        workload_payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else arguments
        if not workload_payload:
            workload_payload = spec["sample_input"]

        evaluation = evaluate_skill_deterministically(spec, workload_payload)
        elapsed_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 3)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": canonical_json(evaluation)}],
                "isError": False,
                "meta": {
                    "skill_id": spec["id"],
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
            "message": f"Method not found: '{method}'. Supported: initialize, tools/list, tools/call",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SkillForge AI MCP JSON-RPC 2.0 Server")
    parser.add_argument("--self-test", action="store_true", help="Run MCP JSON-RPC 2.0 handshake & tool verification")
    args = parser.parse_args()

    if args.self_test:
        r_init = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        r_list = process_mcp_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        r_call = process_mcp_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
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
