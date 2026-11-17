#!/usr/bin/env python3
"""SkillForge AI — Command-Line Compiler & 3-Run Determinism Verifier."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from skillforge.compiler import (
    build_zip_bundle,
    canonical_json,
    compile_skill,
    evaluate_skill_deterministically,
    parse_blueprint_or_preset,
)
from skillforge.presets import PRESETS, list_presets


def write_compiled_artifacts(compiled: Dict[str, Any], out_dir: Path) -> Path:
    """Write all compiled skill files and .zip bundle to out_dir."""
    skill_dir = out_dir / compiled["spec"]["name"]
    skill_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in compiled["artifacts"].items():
        target = skill_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if rel_path.endswith(".py"):
            os.chmod(target, 0o755)

    zip_path = out_dir / f"{compiled['spec']['name']}.zip"
    zip_path.write_bytes(build_zip_bundle(compiled))
    return skill_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skillforge-cli",
        description="SkillForge AI — Compile Web Apps, OpenAPI Specs & Blueprints into Verified Agent Skills",
    )
    parser.add_argument("--list-presets", action="store_true", help="List all 6 built-in industry skill presets.")
    parser.add_argument(
        "--compile",
        metavar="PRESET_OR_JSON",
        help="Compile a built-in preset ID or path to a custom JSON blueprint file.",
    )
    parser.add_argument(
        "--out-dir",
        metavar="DIR",
        help="Optional directory to write compiled SKILL.md, scripts/engine.py, mcp_server.py, and .zip bundle.",
    )
    parser.add_argument(
        "--verify",
        metavar="PRESET_ID",
        help="Run 5-Gate verification and 3-run SHA-256 determinism check on a preset ID or 'all'.",
    )
    args = parser.parse_args()

    if args.list_presets:
        catalog = [
            {
                "id": p["id"],
                "title": p["title"],
                "category": p["category"],
                "version": p["version"],
                "frameworks": p["frameworks"],
                "rules_count": len(p["rules"]),
            }
            for p in list_presets()
        ]
        print(canonical_json({"presets": catalog, "total": len(catalog)}))
        return 0

    if args.verify:
        targets = list(PRESETS.keys()) if args.verify == "all" else [args.verify]
        verification_results = []
        for pid in targets:
            compiled = compile_skill({"preset_id": pid})
            spec = parse_blueprint_or_preset({"preset_id": pid})
            runs = [evaluate_skill_deterministically(spec, spec["sample_input"]) for _ in range(3)]
            hashes = [r["determinism_sha256"] for r in runs]
            verification_results.append(
                {
                    "preset_id": pid,
                    "all_gates_passed": compiled["all_gates_passed"],
                    "deterministic": len(set(hashes)) == 1,
                    "run_1_sha256": hashes[0],
                    "run_2_sha256": hashes[1],
                    "run_3_sha256": hashes[2],
                    "package_sha256": compiled["package_sha256"],
                    "gates": compiled["gates"],
                }
            )
        all_ok = all(v["all_gates_passed"] and v["deterministic"] for v in verification_results)
        print(canonical_json({"verified": all_ok, "results": verification_results}))
        return 0 if all_ok else 1

    if args.compile:
        target_arg = args.compile
        if target_arg in PRESETS:
            payload: Dict[str, Any] = {"preset_id": target_arg}
        elif os.path.isfile(target_arg):
            with open(target_arg, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        else:
            payload = {"name": target_arg, "blueprint": f"Custom skill blueprint for {target_arg}"}

        compiled = compile_skill(payload)
        output_summary: Dict[str, Any] = {
            "skill_id": compiled["spec"]["id"],
            "title": compiled["spec"]["title"],
            "version": compiled["spec"]["version"],
            "all_gates_passed": compiled["all_gates_passed"],
            "package_sha256": compiled["package_sha256"],
            "determinism": compiled["determinism"],
            "stages": compiled["stages"],
            "gates": compiled["gates"],
            "artifacts": list(compiled["artifacts"].keys()),
        }
        if args.out_dir:
            written_dir = write_compiled_artifacts(compiled, Path(args.out_dir))
            output_summary["written_to"] = str(written_dir)
            output_summary["zip_bundle"] = str(Path(args.out_dir) / f"{compiled['spec']['name']}.zip")

        print(canonical_json(output_summary))
        return 0 if compiled["all_gates_passed"] else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
