"""Multi-Skill Sequential Orchestration Layer, Master Executive Reporter & Two-Run Determinism Builder.

Replicates 1:1 the Experimental-Zone multi-skill sequential assessment architecture:
  - Stage 1 Upstream Scope & Group Discovery -> writes `00_Verified_Scope_and_Groups/discovered_items.txt`
  - Stages 2..N Verification, Lockdown, Provenance & Vulnerability SLA Scanners -> consume `--handoff-in`
  - Master Executive Reporter -> synthesizes all stage outputs into:
      * `Canonical_Reviewed_Dataset.json` (`dataset_sha256` + per-stage sub-hashes)
      * `<App>_Finalized_Master_Report.md` (`report_sha256` + 5-Layer Architecture Mermaid Diagram)
      * `Finalized_Master_Executive_Summary.html` (C-Suite standalone dashboard)
      * `Supporting_Annex_Stage_Hashes.csv`
      * `Cryptographic_Verification_Manifest.json`
  - Two-Run Cryptographic Determinism Verifier (`Run_A` vs `Run_B` byte-for-byte SHA-256 equality proof)
  - Unified 1-Command Launcher CLI (`all`, `stage`, `report`, `compare`, `verify`)
"""

from __future__ import annotations

import html
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from skillforge.compiler import canonical_json, normalize_slug, sha256_digest
from skillforge.llm_bridge import _invoke_llm
from skillforge.skill_creator_studio import build_standalone_headless_skill
from skillforge.workspace import REPO_ROOT, SKILLS_WORKSPACE_DIR

PIPELINE_RUNS_DIR = REPO_ROOT / "pipeline_runs"


def _ensure_pipeline_dirs() -> None:
    SKILLS_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)


REFERENCE_COMPLIANCE_STAGES: List[Dict[str, Any]] = [
    {
        "name": "service-acl-scope-discovery",
        "title": "Stage 1 — Production Service ACL & Scope Discovery",
        "stage_role": "discovery",
        "description": (
            "Upstream discovery skill that inventories production service endpoints, storage ACL policies, "
            "and access groups for a target application, strictly excludes dev/test/staging/sandbox configs, "
            "and writes `00_Verified_Handoff/discovered_items.txt` for downstream verification skills. "
            "Use when defining an application compliance boundary or enumerating authorized production groups. "
            "Do not use for non-production sandbox testing."
        ),
    },
    {
        "name": "uar-access-group-auditor",
        "title": "Stage 2 — User Access Review (UAR) Group Auditor",
        "stage_role": "uar",
        "description": (
            "Consumes verified groups from Stage 1 (`--handoff-in`), audits human and service group memberships, "
            "identifies permanent vs. eligible access cohorts and denied/review-required principals, and emits "
            "executive HTML/Markdown/CSV UAR evidence bundles. Use when running User Access Reviews on access groups. "
            "Do not use for network firewall testing."
        ),
    },
    {
        "name": "zero-standing-privilege-checker",
        "title": "Stage 3 — Zero-Standing-Privilege & Role Lockdown Checker",
        "stage_role": "nope",
        "description": (
            "Consumes verified groups from Stage 1 (`--handoff-in`) and verifies machine-only service account "
            "lockdown levels (L0-L6), isolating untagged zero-human groups into a dedicated Review_Required cohort. "
            "Use when auditing zero-standing-privilege or machine-group lockdown compliance. "
            "Do not use for frontend UI styling."
        ),
    },
    {
        "name": "prod-build-provenance-verifier",
        "title": "Stage 4 — Production Build & Config Level-4 Provenance Verifier",
        "stage_role": "provenance",
        "description": (
            "Audits production-only deployment and policy configs from Stage 1 against Level-4 submitted and "
            "authorized provenance requirements, strictly excluding non-prod paths and generating SHA-256 attested "
            "compliance reports. Use when verifying Level-4 build and configuration integrity. "
            "Do not use for local developer prototypes."
        ),
    },
    {
        "name": "vuln-sla-and-7gate-validator",
        "title": "Stage 5 — Vulnerability SLA & 7-Gate False-Positive Validator",
        "stage_role": "vuln",
        "description": (
            "Audits security ticket remediation SLAs across component IDs (`--components`) and applies 7-Gate "
            "adversarial false-positive validation across discovered findings. Use when verifying vulnerability "
            "SLA compliance or validating true-positive vs. false-positive security findings. "
            "Do not use for unapproved production mutations."
        ),
    },
]


def _build_master_reporter_script(pipeline_slug: str, pipeline_title: str) -> str:
    return f'''#!/usr/bin/env python3
"""Master Executive Compliance & Determinism Synthesis Reporter for `{pipeline_slug}`.

Reads all completed stage directories (`Canonical_Results.json`), builds a 5-Layer Architecture
Mermaid diagram, computes `dataset_sha256` + `report_sha256` + per-stage sub-hashes, and writes:
  - Canonical_Reviewed_Dataset.json
  - <App>_Finalized_Master_Report.md
  - Finalized_Master_Executive_Summary.html
  - Supporting_Annex_Stage_Hashes.csv
  - Cryptographic_Verification_Manifest.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
from typing import Any, Dict, List


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def synthesize_master_report(run_root: Path, app_name: str, spec_path: Path) -> Dict[str, Any]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    stages_cfg: List[Dict[str, Any]] = spec.get("stages") or []

    stage_summaries: List[Dict[str, Any]] = []
    consolidated_findings: List[Dict[str, Any]] = []
    stage_sub_hashes: Dict[str, str] = {{}}

    for st in stages_cfg:
        st_num = int(st["stage_number"])
        st_slug = st["slug"]
        st_dir = run_root / f"{{st_num:02d}}_{{st_slug}}"
        canon_file = st_dir / "Canonical_Results.json"
        if not canon_file.is_file():
            continue
        raw_txt = canon_file.read_text(encoding="utf-8")
        st_data = json.loads(raw_txt)
        st_sha = sha256_hex(canonical_json(st_data))
        stage_sub_hashes[st_slug] = st_sha

        findings = st_data.get("findings") or []
        for f in findings:
            enriched = dict(f)
            enriched["stage_slug"] = st_slug
            enriched["stage_number"] = st_num
            consolidated_findings.append(enriched)

        stage_summaries.append({{
            "stage_number": st_num,
            "skill_slug": st_slug,
            "title": st.get("title", st_slug),
            "verdict": st_data.get("verdict", "PASS"),
            "production_items_verified": st_data.get("production_items_verified", 0),
            "non_prod_items_excluded": st_data.get("non_prod_items_excluded", 0),
            "review_required_count": st_data.get("review_required_count", 0),
            "findings_count": len(findings),
            "stage_dataset_sha256": st_sha,
        }})

    master_dir = run_root / f"{{len(stages_cfg) + 1:02d}}_Finalized_Master_Report"
    master_dir.mkdir(parents=True, exist_ok=True)

    total_verified = sum(s["production_items_verified"] for s in stage_summaries)
    total_excluded = sum(s["non_prod_items_excluded"] for s in stage_summaries)
    total_review = sum(s["review_required_count"] for s in stage_summaries)
    overall_verdict = "PASS_WITH_REVIEW_COHORT" if total_review > 0 else "PASS"

    canonical_dataset = {{
        "orchestrator": "{pipeline_slug}",
        "pipeline_title": {json.dumps(pipeline_title)},
        "target_application": app_name,
        "overall_verdict": overall_verdict,
        "stages_completed": len(stage_summaries),
        "total_production_items_verified": total_verified,
        "total_non_prod_items_excluded": total_excluded,
        "total_review_required_items": total_review,
        "stage_sub_hashes": {{k: stage_sub_hashes[k] for k in sorted(stage_sub_hashes.keys())}},
        "stage_summaries": stage_summaries,
        "consolidated_findings": consolidated_findings,
    }}
    dataset_str = canonical_json(canonical_dataset)
    dataset_sha = sha256_hex(dataset_str)

    dataset_path = master_dir / "Canonical_Reviewed_Dataset.json"
    dataset_path.write_text(dataset_str + "\\n", encoding="utf-8")

    # Supporting Annex CSV
    annex_csv = master_dir / "Supporting_Annex_Stage_Hashes.csv"
    with annex_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["stage_number", "skill_slug", "verdict", "prod_verified", "non_prod_excluded", "review_required", "stage_dataset_sha256"])
        for s in stage_summaries:
            writer.writerow([
                s["stage_number"],
                s["skill_slug"],
                s["verdict"],
                s["production_items_verified"],
                s["non_prod_items_excluded"],
                s["review_required_count"],
                s["stage_dataset_sha256"],
            ])

    # 5-Layer Architecture Mermaid Diagram + Master Markdown Report
    safe_app = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in app_name).strip("_") or "TargetApp"
    stage_nodes_mermaid = "\\n".join(
        f'    S{{s["stage_number"]}}["Stage {{s["stage_number"]}}: {{s["skill_slug"]}}"]'
        for s in stage_summaries
    )
    stage_edges_mermaid = "\\n".join(
        f'    Handoff --> S{{s["stage_number"]}} --> Master'
        for s in stage_summaries[1:]
    ) if len(stage_summaries) > 1 else "    Handoff --> Master"
    first_node = f'S{{stage_summaries[0]["stage_number"]}}' if stage_summaries else "S1"

    md_lines = [
        f"# {{app_name}} — {pipeline_title} (Finalized Master Report)",
        "",
        f"- **Orchestrator Skill:** `{pipeline_slug}`",
        f"- **Target Application:** `{{app_name}}`",
        f"- **Overall Assessment Verdict:** `{{overall_verdict}}`",
        f"- **Stages Executed:** `{{len(stage_summaries)}}`",
        f"- **Production Items Verified:** `{{total_verified}}` (Non-Prod Excluded: `{{total_excluded}}`)",
        f"- **Canonical Reviewed Dataset SHA-256:** `{{dataset_sha}}`",
        "",
        "## 5-Layer Sequential Verification & Cryptographic Attestation Architecture",
        "",
        "```mermaid",
        "flowchart TD",
        f'    Target["Layer 1: Target System ({{app_name}})"]',
        f'    {{first_node}}["Layer 2: Upstream Scope Discovery"]',
        '    Handoff["Layer 3: 00_Verified_Scope_and_Groups / discovered_items.txt"]',
        stage_nodes_mermaid,
        '    Master["Layer 4: Master Synthesis & Canonical_Reviewed_Dataset.json"]',
        '    Verify["Layer 5: Two-Run SHA-256 Cryptographic Determinism Proof"]',
        f"    Target --> {{first_node}} --> Handoff",
        stage_edges_mermaid,
        "    Master --> Verify",
        "```",
        "",
        "## Stage-by-Stage Verification Rollup & Sub-Hashes",
        "",
        "| Stage | Skill | Verdict | Prod Verified | Non-Prod Excluded | Review Cohort | Stage SHA-256 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for s in stage_summaries:
        md_lines.append(
            f"| {{s['stage_number']}} | `{{s['skill_slug']}}` | **{{s['verdict']}}** | {{s['production_items_verified']}} | "
            f"{{s['non_prod_items_excluded']}} | {{s['review_required_count']}} | `{{s['stage_dataset_sha256'][:16]}}...` |"
        )

    md_lines.extend([
        "",
        "## Consolidated Production Findings",
        "",
        "| Stage | Finding ID | Item | Severity | Status |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])
    for f in consolidated_findings:
        md_lines.append(
            f"| Stage {{f['stage_number']}} (`{{f['stage_slug']}}`) | {{f.get('id','')}} | `{{f.get('item','')}}` | {{f.get('severity','')}} | **{{f.get('status','')}}** |"
        )

    md_text = "\\n".join(md_lines) + "\\n"
    report_sha = sha256_hex(md_text)
    md_path = master_dir / f"{{safe_app}}_Finalized_Master_Report.md"
    md_path.write_text(md_text, encoding="utf-8")

    # C-Suite Standalone HTML Summary
    stage_rows_html = "".join(
        f"<tr><td>Stage {{s['stage_number']}}</td><td><code>{{html.escape(s['skill_slug'])}}</code></td>"
        f"<td><strong>{{html.escape(s['verdict'])}}</strong></td><td>{{s['production_items_verified']}}</td>"
        f"<td>{{s['non_prod_items_excluded']}}</td><td>{{s['review_required_count']}}</td>"
        f"<td><code>{{s['stage_dataset_sha256'][:20]}}...</code></td></tr>"
        for s in stage_summaries
    )
    css_styles = (
        "body {{ font-family: system-ui, sans-serif; background:#090d16; color:#f8fafc; padding:32px; margin:0; }} "
        ".wrap {{ max-width:1160px; margin:0 auto; background:#111827; border:1px solid #1f2937; border-radius:14px; padding:28px; }} "
        ".kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:18px 0; }} "
        ".kpi {{ background:#0b0f19; border:1px solid #334155; border-radius:10px; padding:14px; }} "
        ".kpi .val {{ font-size:22px; font-weight:800; color:#38bdf8; }} "
        "table {{ width:100%; border-collapse:collapse; margin-top:16px; font-size:13px; }} "
        "th, td {{ border:1px solid #1f2937; padding:10px; text-align:left; }} "
        "th {{ background:#0b0f19; color:#a5b4fc; }} code {{ color:#6ee7b7; }} "
        ".hashes {{ margin-top:18px; padding:12px; background:#0b0f19; border-radius:8px; font-family:monospace; font-size:12px; color:#94a3b8; }}"
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{{html.escape(app_name)}} — Master Executive Report</title>
<style>{{css_styles}}</style></head><body><div class="wrap">
<h1>{{html.escape(app_name)}} — {html.escape(pipeline_title)}</h1>
<p><strong>Overall Verdict:</strong> <code>{{html.escape(overall_verdict)}}</code></p>
<div class="kpis">
  <div class="kpi"><div>Stages Executed</div><div class="val">{{len(stage_summaries)}}</div></div>
  <div class="kpi"><div>Prod Items Verified</div><div class="val">{{total_verified}}</div></div>
  <div class="kpi"><div>Non-Prod Excluded</div><div class="val">{{total_excluded}}</div></div>
  <div class="kpi"><div>Review Required</div><div class="val">{{total_review}}</div></div>
</div>
<table><thead><tr><th>Stage</th><th>Skill</th><th>Verdict</th><th>Prod Verified</th><th>Non-Prod Excluded</th><th>Review Cohort</th><th>Stage SHA-256</th></tr></thead>
<tbody>{{stage_rows_html}}</tbody></table>
<div class="hashes">
  Canonical_Reviewed_Dataset.json SHA-256: {{dataset_sha}}<br>
  Finalized_Master_Report.md SHA-256: {{report_sha}}
</div>
</div></body></html>"""
    html_path = master_dir / "Finalized_Master_Executive_Summary.html"
    html_path.write_text(html_doc, encoding="utf-8")

    manifest = {{
        "orchestrator": "{pipeline_slug}",
        "target_application": app_name,
        "overall_verdict": overall_verdict,
        "dataset_sha256": dataset_sha,
        "report_sha256": report_sha,
        "stage_sub_hashes": {{k: stage_sub_hashes[k] for k in sorted(stage_sub_hashes.keys())}},
        "files": {{
            "canonical_dataset_json": str(dataset_path),
            "master_markdown_report": str(md_path),
            "master_executive_html": str(html_path),
            "annex_stage_hashes_csv": str(annex_csv),
        }},
    }}
    manifest_path = master_dir / "Cryptographic_Verification_Manifest.json"
    manifest_path.write_text(canonical_json(manifest) + "\\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Synthesize Master Executive Report across completed pipeline stages.")
    ap.add_argument("--run-dir", required=True, help="Root directory of the pipeline run")
    ap.add_argument("--app", default="PaymentsCore", help="Target application name")
    ap.add_argument("--spec", default="", help="Optional path to pipeline_spec.json")
    args = ap.parse_args()

    spec_path = Path(args.spec) if args.spec else (Path(__file__).resolve().parent.parent / "pipeline_spec.json")
    res = synthesize_master_report(Path(args.run_dir), args.app, spec_path)
    print(canonical_json(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _build_orchestrator_runner_script(pipeline_slug: str) -> str:
    return f'''#!/usr/bin/env python3
"""Sequential Multi-Skill Orchestration Engine for `{pipeline_slug}`.

Executes Stage 1 discovery -> consolidates `00_Verified_Scope_and_Groups/discovered_items.txt` ->
executes Stages 2..N sequentially with `--handoff-in` -> synthesizes Finalized Master Report.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ORCH_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = ORCH_ROOT.parent
if str(ORCH_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT / "scripts"))

from generate_master_report import canonical_json, synthesize_master_report  # noqa: E402


def run_pipeline(
    app_name: str,
    out_dir: Path,
    components: str = "",
    only_stage: str = "",
) -> Dict[str, Any]:
    spec_path = ORCH_ROOT / "pipeline_spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    stages: List[Dict[str, Any]] = spec.get("stages") or []

    out_dir.mkdir(parents=True, exist_ok=True)
    consolidated_handoff_dir = out_dir / "00_Verified_Scope_and_Groups"
    consolidated_handoff_dir.mkdir(parents=True, exist_ok=True)
    handoff_file = consolidated_handoff_dir / "discovered_items.txt"

    stage_runs: List[Dict[str, Any]] = []

    for st in stages:
        st_num = int(st["stage_number"])
        st_slug = st["slug"]
        if only_stage and only_stage not in (str(st_num), st_slug):
            continue

        skill_dir = WORKSPACE_ROOT / st_slug
        cli_rel = st.get("cli_script") or f"scripts/{{st_slug.replace('-', '_')}}_cli.py"
        cli_path = skill_dir / cli_rel
        if not cli_path.is_file():
            alt = skill_dir / "scripts" / "engine.py"
            cli_path = alt if alt.is_file() else cli_path

        stage_out_dir = out_dir / f"{{st_num:02d}}_{{st_slug}}"
        stage_out_dir.mkdir(parents=True, exist_ok=True)

        if cli_path.name == "engine.py":
            cmd = [sys.executable, str(cli_path), "--out-dir", str(stage_out_dir)]
        else:
            cmd = [sys.executable, str(cli_path), "--app", app_name, "--out-dir", str(stage_out_dir)]
            if st_num > 1 and handoff_file.is_file():
                cmd.extend(["--handoff-in", str(handoff_file)])
            if components:
                cmd.extend(["--components", components])

        proc = subprocess.run(cmd, cwd=str(skill_dir), capture_output=True, text=True, check=True)
        parsed_out = json.loads(proc.stdout) if (proc.stdout or "").strip().startswith("{{") else {{"raw": proc.stdout}}

        # If Stage 1 produced 00_Verified_Handoff/discovered_items.txt, promote to 00_Verified_Scope_and_Groups/
        st_handoff = stage_out_dir / "00_Verified_Handoff" / "discovered_items.txt"
        if st_num == 1 and st_handoff.is_file():
            shutil.copyfile(st_handoff, handoff_file)
            ver_src = stage_out_dir / "00_Verified_Handoff" / "discovered_items_verification.csv"
            if ver_src.is_file():
                shutil.copyfile(ver_src, consolidated_handoff_dir / "discovered_items_verification.csv")

        stage_runs.append({{
            "stage_number": st_num,
            "skill_slug": st_slug,
            "title": st.get("title", st_slug),
            "stage_out_dir": str(stage_out_dir),
            "dataset_sha256": parsed_out.get("dataset_sha256", parsed_out.get("determinism_sha256", "")),
            "verdict": parsed_out.get("verdict", "PASS"),
            "production_items_verified": parsed_out.get("production_items_verified", 0),
        }})

    master_manifest = {{}}
    if not only_stage:
        master_manifest = synthesize_master_report(out_dir, app_name, spec_path)

    handoff_items = (
        [ln.strip() for ln in handoff_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if handoff_file.is_file()
        else []
    )
    return {{
        "ok": True,
        "orchestrator": "{pipeline_slug}",
        "target_application": app_name,
        "run_dir": str(out_dir),
        "verified_handoff_file": str(handoff_file),
        "verified_handoff_count": len(handoff_items),
        "verified_handoff_items": handoff_items,
        "stages_executed": stage_runs,
        "master_report": master_manifest,
    }}


def main() -> int:
    ap = argparse.ArgumentParser(description="Run sequential multi-skill orchestrator pipeline.")
    ap.add_argument("--app", default="PaymentsCore", help="Target application name")
    ap.add_argument("--out-dir", required=True, help="Output directory for sequential stage artifacts")
    ap.add_argument("--components", default="", help="Optional comma-separated component IDs")
    ap.add_argument("--stage", default="", help="Optional single stage number or skill slug to execute")
    args = ap.parse_args()

    res = run_pipeline(args.app, Path(args.out_dir), components=args.components, only_stage=args.stage)
    print(canonical_json(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _build_two_run_verifier_script(pipeline_slug: str) -> str:
    return f'''#!/usr/bin/env python3
"""Two-Run Independent Cryptographic Determinism Verifier for `{pipeline_slug}`.

Supports:
  1. `verify` mode: Executes full orchestrated pipeline twice in clean directories (`Run_A/` and `Run_B/`)
     and proves `Run A SHA-256 == Run B SHA-256` across dataset, master report, and every stage sub-hash.
  2. `compare` mode: Compares two existing pipeline run directories (`--run-a`, `--run-b`).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

ORCH_ROOT = Path(__file__).resolve().parent.parent
if str(ORCH_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT / "scripts"))

from generate_master_report import canonical_json  # noqa: E402
from run_orchestrator import run_pipeline  # noqa: E402


def _find_manifest(run_dir: Path) -> Dict[str, Any]:
    matches = sorted(run_dir.glob("*_Finalized_Master_Report/Cryptographic_Verification_Manifest.json"))
    if not matches:
        raise FileNotFoundError(f"Cryptographic_Verification_Manifest.json not found under {{run_dir}}")
    return json.loads(matches[-1].read_text(encoding="utf-8"))


def compare_two_runs(run_a_dir: Path, run_b_dir: Path, out_report_dir: Path) -> Dict[str, Any]:
    man_a = _find_manifest(run_a_dir)
    man_b = _find_manifest(run_b_dir)

    dataset_match = man_a["dataset_sha256"] == man_b["dataset_sha256"]
    report_match = man_a["report_sha256"] == man_b["report_sha256"]

    stage_comparisons = []
    all_stage_keys = sorted(set(man_a.get("stage_sub_hashes", {{}}).keys()) | set(man_b.get("stage_sub_hashes", {{}}).keys()))
    for k in all_stage_keys:
        ha = man_a.get("stage_sub_hashes", {{}}).get(k, "")
        hb = man_b.get("stage_sub_hashes", {{}}).get(k, "")
        stage_comparisons.append({{
            "stage_slug": k,
            "run_a_sha256": ha,
            "run_b_sha256": hb,
            "identical": ha == hb and bool(ha),
        }})

    all_stages_identical = all(x["identical"] for x in stage_comparisons)
    deterministic = bool(dataset_match and report_match and all_stages_identical)

    proof = {{
        "orchestrator": "{pipeline_slug}",
        "deterministic": deterministic,
        "verdict": "CRYPTOGRAPHICALLY_IDENTICAL_PASS" if deterministic else "DRIFT_DETECTED_FAIL",
        "dataset_sha256_run_a": man_a["dataset_sha256"],
        "dataset_sha256_run_b": man_b["dataset_sha256"],
        "dataset_identical": dataset_match,
        "report_sha256_run_a": man_a["report_sha256"],
        "report_sha256_run_b": man_b["report_sha256"],
        "report_identical": report_match,
        "stage_hash_comparisons": stage_comparisons,
    }}

    out_report_dir.mkdir(parents=True, exist_ok=True)
    proof_json = out_report_dir / "Two_Run_Determinism_Proof.json"
    proof_json.write_text(canonical_json(proof) + "\\n", encoding="utf-8")

    md_lines = [
        f"# Two-Run Cryptographic Determinism Verification — `{pipeline_slug}`",
        "",
        f"- **Determinism Verdict:** `{{proof['verdict']}}`",
        f"- **Dataset SHA-256 Match:** `{{dataset_match}}` (`{{man_a['dataset_sha256']}}`)",
        f"- **Master Report SHA-256 Match:** `{{report_match}}` (`{{man_a['report_sha256']}}`)",
        "",
        "## Per-Stage SHA-256 Comparison (`Run_A` vs `Run_B`)",
        "",
        "| Stage Skill | Run A SHA-256 | Run B SHA-256 | Byte-for-Byte Match |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for sc in stage_comparisons:
        md_lines.append(
            f"| `{{sc['stage_slug']}}` | `{{sc['run_a_sha256'][:20]}}...` | `{{sc['run_b_sha256'][:20]}}...` | **{{'PASS' if sc['identical'] else 'FAIL'}}** |"
        )
    proof_md = out_report_dir / "Two_Run_Determinism_Comparison_Report.md"
    proof_md.write_text("\\n".join(md_lines) + "\\n", encoding="utf-8")

    proof["proof_files"] = {{"json": str(proof_json), "markdown": str(proof_md)}}
    return proof


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify two-run SHA-256 determinism across the full pipeline.")
    ap.add_argument("--mode", choices=["verify", "compare"], default="verify")
    ap.add_argument("--app", default="PaymentsCore")
    ap.add_argument("--components", default="")
    ap.add_argument("--base-dir", default="")
    ap.add_argument("--run-a", default="")
    ap.add_argument("--run-b", default="")
    args = ap.parse_args()

    if args.mode == "compare":
        ra, rb = Path(args.run_a), Path(args.run_b)
        out = ra.parent / "Determinism_Comparison"
        res = compare_two_runs(ra, rb, out)
        print(canonical_json(res))
        return 0 if res["deterministic"] else 1

    base = Path(args.base_dir) if args.base_dir else (ORCH_ROOT / "determinism_runs" / args.app)
    if base.exists():
        shutil.rmtree(base)
    run_a_dir = base / "Run_A"
    run_b_dir = base / "Run_B"
    run_a = run_pipeline(args.app, run_a_dir, components=args.components)
    run_b = run_pipeline(args.app, run_b_dir, components=args.components)
    proof = compare_two_runs(run_a_dir, run_b_dir, base / "Determinism_Proof")
    proof["run_a_summary"] = run_a["master_report"]
    proof["run_b_summary"] = run_b["master_report"]
    proof["verified_handoff_items"] = run_a["verified_handoff_items"]
    print(canonical_json(proof))
    return 0 if proof["deterministic"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _build_unified_cli_launcher(pipeline_slug: str, launcher_name: str) -> str:
    return f'''#!/usr/bin/env python3
"""Unified 1-Command Assessment & Orchestration CLI Launcher (`{launcher_name}`).

Commands:
  ./{launcher_name} list
  ./{launcher_name} stage <stage_num_or_slug> <app_name> [--out-dir DIR]
  ./{launcher_name} all <app_name> [--components 101,202] [--out-dir DIR]
  ./{launcher_name} report <run_dir> <app_name>
  ./{launcher_name} compare <run_dir_a> <run_dir_b>
  ./{launcher_name} verify <app_name> [--components 101,202]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0

    cmd = argv[0]
    spec = json.loads((HERE / "pipeline_spec.json").read_text(encoding="utf-8"))

    if cmd == "list":
        print(json.dumps(spec, indent=2))
        return 0

    if cmd == "stage" and len(argv) >= 3:
        st, app = argv[1], argv[2]
        out = HERE / "runs" / f"{{app}}_stage_{{st}}"
        return subprocess.call([sys.executable, str(HERE / "scripts/run_orchestrator.py"), "--stage", st, "--app", app, "--out-dir", str(out)] + argv[3:])

    if cmd == "all":
        app = argv[1] if len(argv) >= 2 else "PaymentsCore"
        out = HERE / "runs" / f"{{app}}_full"
        return subprocess.call([sys.executable, str(HERE / "scripts/run_orchestrator.py"), "--app", app, "--out-dir", str(out)] + argv[2:])

    if cmd == "report" and len(argv) >= 2:
        run_dir = argv[1]
        app = argv[2] if len(argv) >= 3 else "PaymentsCore"
        return subprocess.call([sys.executable, str(HERE / "scripts/generate_master_report.py"), "--run-dir", run_dir, "--app", app])

    if cmd == "compare" and len(argv) >= 3:
        return subprocess.call([sys.executable, str(HERE / "scripts/verify_determinism.py"), "--mode", "compare", "--run-a", argv[1], "--run-b", argv[2]])

    if cmd == "verify":
        app = argv[1] if len(argv) >= 2 else "PaymentsCore"
        return subprocess.call([sys.executable, str(HERE / "scripts/verify_determinism.py"), "--mode", "verify", "--app", app] + argv[2:])

    print(f"Unknown command: {{cmd}}\\n" + __doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
'''


def compile_custom_orchestrator(
    pipeline_name: str,
    stage_skill_slugs: List[str],
    description: str = "",
    llm_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compile any ordered sequence of installed workspace skills into a full Multi-Skill
    Sequential Orchestrator + Master Synthesis Reporter + Unified CLI Launcher skill.
    """
    _ensure_pipeline_dirs()
    raw_slug = normalize_slug(pipeline_name or "compliance-master-orchestrator")
    pipeline_slug = raw_slug if raw_slug.endswith("orchestrator") else f"{raw_slug}-orchestrator"
    pipeline_title = pipeline_name.strip() if pipeline_name.strip() and "-" not in pipeline_name else pipeline_slug.replace("-", " ").title()
    launcher_name = pipeline_slug.replace("-orchestrator", "") + "-cli"

    if not stage_skill_slugs:
        raise ValueError("Provide at least 1 stage skill slug to compile an orchestrator.")

    stages_spec: List[Dict[str, Any]] = []
    for idx, raw_st in enumerate(stage_skill_slugs, start=1):
        st_slug = normalize_slug(raw_st)
        st_dir = SKILLS_WORKSPACE_DIR / st_slug
        if not st_dir.is_dir():
            build_standalone_headless_skill({"name": st_slug})
        man_p = st_dir / "skill_manifest.json"
        man = json.loads(man_p.read_text(encoding="utf-8")) if man_p.is_file() else {}
        stages_spec.append(
            {
                "stage_number": idx,
                "slug": st_slug,
                "title": man.get("title") or st_slug.replace("-", " ").title(),
                "cli_script": man.get("cli_script") or (
                    f"scripts/{st_slug.replace('-', '_')}_cli.py"
                    if (st_dir / f"scripts/{st_slug.replace('-', '_')}_cli.py").is_file()
                    else "scripts/engine.py"
                ),
                "consumes_stage_1_handoff": idx > 1,
            }
        )

    clean_desc = (description or "").strip() or (
        f"Sequential multi-skill orchestrator and master executive synthesis skill ({len(stages_spec)} stages) "
        f"that runs upstream production scope discovery first, passes `00_Verified_Scope_and_Groups/discovered_items.txt` "
        f"to all downstream verification/scanner skills, synthesizes `Canonical_Reviewed_Dataset.json` + "
        f"`Finalized_Master_Executive_Summary.html` + 5-Layer Architecture Mermaid report, and proves Two-Run "
        f"SHA-256 cryptographic determinism (`Run A == Run B`). Use when running an end-to-end multi-skill workflow."
    )

    llm_note = ""
    llm_model_used = "deterministic-compiler"
    if llm_config:
        try:
            txt, model_name = _invoke_llm(
                llm_config,
                "Write a concise 3-sentence executive summary explaining why sequential stage handoffs and two-run SHA-256 verification prevent agent drift.",
                f"Pipeline: {pipeline_title}\nStages: {[s['slug'] for s in stages_spec]}",
                json_mode=False,
                max_tokens=160,
                timeout_sec=14.0,
            )
            if txt.strip():
                llm_note = f"\n## Architectural Rationale (Synthesized via `{model_name}`)\n\n{txt.strip()}\n"
                llm_model_used = model_name
        except Exception:
            pass

    stage_table_md = "\n".join(
        f"| **Stage {s['stage_number']}** | `{s['slug']}` | {s['title']} | `{'Writes 00_Verified_Scope_and_Groups/' if s['stage_number'] == 1 else 'Consumes --handoff-in'}` |"
        for s in stages_spec
    )

    skill_md = f"""---
name: {pipeline_slug}
description: >-
  {clean_desc}
---

# {pipeline_title} (`{pipeline_slug}`)

End-to-end sequential orchestration skill, Master Executive Reporter, and Two-Run SHA-256 Determinism Verifier across **{len(stages_spec)} standalone skills**.
{llm_note}
## Sequential Execution Order & Disk Handoff Contract

| Stage | Skill Slug | Role | Data Handoff Contract |
| :--- | :--- | :--- | :--- |
{stage_table_md}

## Unified 1-Command CLI Usage (`./{launcher_name}`)

```bash
# 1. Run full sequential assessment + Master Executive Report
./{launcher_name} all PaymentsCore --components 10401,10402

# 2. Run a single stage standalone
./{launcher_name} stage 1 PaymentsCore

# 3. Execute Two-Run Independent SHA-256 Determinism Verification (Run A == Run B)
./{launcher_name} verify PaymentsCore --components 10401,10402

# 4. Compare two existing run directories byte-for-byte
./{launcher_name} compare ./Run_A ./Run_B
```
"""

    pipeline_spec = {
        "orchestrator_slug": pipeline_slug,
        "title": pipeline_title,
        "launcher_cli": launcher_name,
        "stages": stages_spec,
    }

    build_bazel = f"""package(default_visibility = ["//visibility:public"])

filegroup(
    name = "{pipeline_slug}",
    srcs = glob([
        "SKILL.md",
        "README.md",
        "INSTALL.md",
        "pipeline_spec.json",
        "{launcher_name}",
        "scripts/**",
    ]),
)
"""

    install_md = f"""# Installing `{pipeline_slug}` & Member Skills

1. Copy `{pipeline_slug}` and all {len(stages_spec)} member skill folders into the same skills directory (e.g., `~/.claude/skills/` or `./skills_workspace/`).
2. Run `./{pipeline_slug}/{launcher_name} verify PaymentsCore` to execute the full sequential pipeline twice and verify `Run A SHA-256 == Run B SHA-256`.
"""

    artifacts: Dict[str, str] = {
        "SKILL.md": skill_md,
        "pipeline_spec.json": canonical_json(pipeline_spec) + "\n",
        "scripts/generate_master_report.py": _build_master_reporter_script(pipeline_slug, pipeline_title),
        "scripts/run_orchestrator.py": _build_orchestrator_runner_script(pipeline_slug),
        "scripts/verify_determinism.py": _build_two_run_verifier_script(pipeline_slug),
        launcher_name: _build_unified_cli_launcher(pipeline_slug, launcher_name),
        "BUILD.bazel": build_bazel,
        "INSTALL.md": install_md,
        "README.md": f"# {pipeline_title}\n\nSequential orchestrator across {len(stages_spec)} skills with unified `./{launcher_name}` CLI.\n",
    }

    orch_dir = SKILLS_WORKSPACE_DIR / pipeline_slug
    if orch_dir.exists():
        shutil.rmtree(orch_dir)
    orch_dir.mkdir(parents=True, exist_ok=True)

    for rel, content in artifacts.items():
        dest = orch_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        if rel.endswith(".py") or rel == launcher_name:
            os.chmod(dest, 0o755)

    manifest = {
        "id": pipeline_slug,
        "name": pipeline_slug,
        "title": pipeline_title,
        "mode": "multi_skill_orchestrator",
        "description": clean_desc,
        "launcher_cli": launcher_name,
        "stages": stages_spec,
        "llm_model_used": llm_model_used,
        "package_sha256": sha256_digest(canonical_json(artifacts)),
        "tools": [
            {
                "name": f"{pipeline_slug.replace('-', '_')}__run_all",
                "description": f"Execute all {len(stages_spec)} stages sequentially and synthesize the Master Executive Report.",
                "kind": "orchestrator_cli",
            },
            {
                "name": f"{pipeline_slug.replace('-', '_')}__verify_two_run_determinism",
                "description": f"Execute Run A and Run B independently and verify identical SHA-256 hashes across {pipeline_slug}.",
                "kind": "orchestrator_cli",
            },
        ],
        "files": sorted(artifacts.keys()),
        "workspace_dir": str(orch_dir),
    }
    (orch_dir / "skill_manifest.json").write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    return {"manifest": manifest, "artifacts": artifacts}


def provision_compliance_reference_suite(llm_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Install the complete 5-stage compliance discovery/verification skill suite + Master Orchestrator."""
    _ensure_pipeline_dirs()
    built_stages = []
    stage_slugs = []
    for st in REFERENCE_COMPLIANCE_STAGES:
        res = build_standalone_headless_skill(st)
        built_stages.append(res["manifest"])
        stage_slugs.append(res["manifest"]["name"])

    orch = compile_custom_orchestrator(
        pipeline_name="compliance-master-orchestrator",
        stage_skill_slugs=stage_slugs,
        llm_config=llm_config,
    )
    return {
        "orchestrator": orch["manifest"],
        "member_skills": built_stages,
        "total_skills_provisioned": len(built_stages) + 1,
    }


def list_orchestrator_pipelines() -> List[Dict[str, Any]]:
    """Return all compiled orchestrator skills currently installed in `skills_workspace/`."""
    _ensure_pipeline_dirs()
    pipelines: List[Dict[str, Any]] = []
    for child in sorted(SKILLS_WORKSPACE_DIR.iterdir()):
        spec_p = child / "pipeline_spec.json"
        man_p = child / "skill_manifest.json"
        if child.is_dir() and spec_p.is_file():
            spec = json.loads(spec_p.read_text(encoding="utf-8"))
            man = json.loads(man_p.read_text(encoding="utf-8")) if man_p.is_file() else {}
            pipelines.append({
                "slug": child.name,
                "title": spec.get("title", child.name),
                "launcher_cli": spec.get("launcher_cli", ""),
                "stages": spec.get("stages", []),
                "package_sha256": man.get("package_sha256", ""),
            })
    return pipelines


def execute_orchestrator_pipeline(
    pipeline_slug: str,
    target_app: str = "PaymentsCore",
    component_ids: str = "10401,10402",
    run_mode: str = "full_workflow",
    stage_selector: str = "",
) -> Dict[str, Any]:
    """Execute a compiled orchestrator via real subprocess (`single_stage`, `full_workflow`, or `two_run_determinism`)."""
    _ensure_pipeline_dirs()
    slug = normalize_slug(pipeline_slug)
    orch_dir = SKILLS_WORKSPACE_DIR / slug
    if not (orch_dir / "pipeline_spec.json").is_file():
        provision_compliance_reference_suite()
        slug = "compliance-master-orchestrator"
        orch_dir = SKILLS_WORKSPACE_DIR / slug

    safe_app = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in target_app).strip("_") or "PaymentsCore"

    if run_mode == "two_run_determinism":
        base_dir = PIPELINE_RUNS_DIR / f"{slug}_{safe_app}_two_run"
        cmd = [
            sys.executable,
            str(orch_dir / "scripts/verify_determinism.py"),
            "--mode",
            "verify",
            "--app",
            target_app,
            "--base-dir",
            str(base_dir),
        ]
        if component_ids:
            cmd.extend(["--components", component_ids])
        proc = subprocess.run(cmd, cwd=str(orch_dir), capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
        md_file = Path(data["proof_files"]["markdown"])
        data["comparison_markdown_preview"] = md_file.read_text(encoding="utf-8") if md_file.is_file() else ""
        return data

    out_dir = PIPELINE_RUNS_DIR / f"{slug}_{safe_app}_{run_mode}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = [
        sys.executable,
        str(orch_dir / "scripts/run_orchestrator.py"),
        "--app",
        target_app,
        "--out-dir",
        str(out_dir),
    ]
    if component_ids:
        cmd.extend(["--components", component_ids])
    if run_mode == "single_stage" and stage_selector:
        cmd.extend(["--stage", str(stage_selector)])

    proc = subprocess.run(cmd, cwd=str(orch_dir), capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
    master_md_path = (data.get("master_report") or {}).get("files", {}).get("master_markdown_report", "")
    if master_md_path and Path(master_md_path).is_file():
        data["master_markdown_preview"] = Path(master_md_path).read_text(encoding="utf-8")
    return data


def build_orchestrator_suite_zip(pipeline_slug: str) -> bytes:
    """Bundle the orchestrator skill + all member stage skills + top-level launcher README into a portable `.zip`."""
    slug = normalize_slug(pipeline_slug or "compliance-master-orchestrator")
    orch_dir = SKILLS_WORKSPACE_DIR / slug
    if not (orch_dir / "pipeline_spec.json").is_file():
        provision_compliance_reference_suite()
        slug = "compliance-master-orchestrator"
        orch_dir = SKILLS_WORKSPACE_DIR / slug

    spec = json.loads((orch_dir / "pipeline_spec.json").read_text(encoding="utf-8"))
    included_dirs = [slug] + [s["slug"] for s in spec.get("stages", [])]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for s_slug in included_dirs:
            s_dir = SKILLS_WORKSPACE_DIR / s_slug
            if not s_dir.is_dir():
                continue
            for p in sorted(s_dir.rglob("*")):
                if not p.is_file():
                    continue
                if any(skip in p.parts for skip in ("__pycache__", "runs", "determinism_runs")):
                    continue
                rel = p.relative_to(s_dir).as_posix()
                info = zipfile.ZipInfo(f"{slug}-suite/{s_slug}/{rel}")
                info.date_time = (2026, 1, 1, 0, 0, 0)
                info.external_attr = (0o755 if p.suffix == ".py" or rel == spec.get("launcher_cli") else 0o644) << 16
                zf.writestr(info, p.read_bytes())
    return buf.getvalue()
