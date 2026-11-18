"""Local PC Application Scanner & Multi-Skill / Multi-Tool MCP Workspace Manager."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from skillforge.compiler import (
    canonical_json,
    compile_skill,
    evaluate_skill_deterministically,
    introspect_webapp_source,
    normalize_slug,
    sha256_digest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_WORKSPACE_DIR = REPO_ROOT / "skills_workspace"

APP_CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".json", ".yaml", ".yml"}
SKIP_SCAN_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".next"}


def browse_pc_directory(raw_path: Optional[str] = None) -> Dict[str, Any]:
    """Browse directories and application files on the local PC."""
    if not raw_path or not raw_path.strip():
        target = REPO_ROOT.parent if REPO_ROOT.parent.exists() else Path.home()
    else:
        target = Path(os.path.expanduser(raw_path.strip())).resolve()

    if not target.exists():
        target = Path.home()
    if target.is_file():
        target = target.parent

    entries: List[Dict[str, Any]] = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith(".") and child.name not in (".", ".."):
                continue
            if child.name in SKIP_SCAN_DIRS:
                continue
            if child.is_dir():
                # Check if directory looks like an application (has server.py, app.py, package.json, index.html, etc.)
                markers = [
                    m for m in ("server.py", "app.py", "main.py", "package.json", "index.html", "openapi.json", "run.sh")
                    if (child / m).exists()
                ]
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "type": "directory",
                    "is_app_candidate": len(markers) > 0,
                    "app_markers": markers,
                })
            elif child.suffix.lower() in APP_CODE_EXTS:
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "type": "file",
                    "size_bytes": child.stat().st_size,
                })
    except PermissionError:
        pass

    return {
        "current_path": str(target),
        "parent_path": str(target.parent) if target.parent != target else str(target),
        "entries": entries[:120],
    }


def scan_pc_application_folder(target_path: str, max_files: int = 20) -> Dict[str, Any]:
    """Scan a selected application directory or file on the user's PC, aggregate its routes
    and functions across all source files, and return a unified multi-tool application blueprint.
    """
    p = Path(os.path.expanduser(target_path.strip())).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Application path does not exist: {target_path}")

    collected_files: List[Path] = []
    if p.is_file():
        collected_files.append(p)
        app_name = p.stem
    else:
        app_name = p.name
        # Prioritize backend/router/entry files first
        priority_names = {"server.py", "app.py", "main.py", "routes.py", "api.py", "engine.py", "index.js", "server.js", "routes.js", "openapi.json", "index.html"}
        all_candidates: List[Path] = []
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_SCAN_DIRS and not d.startswith(".")]
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix.lower() in APP_CODE_EXTS and fpath.stat().st_size <= 350_000:
                    all_candidates.append(fpath)
        all_candidates.sort(key=lambda fp: (0 if fp.name in priority_names else (1 if fp.suffix == ".py" else 2), fp.name))
        collected_files = all_candidates[:max_files]

    combined_chunks: List[str] = []
    file_summaries: List[Dict[str, Any]] = []
    for fp in collected_files:
        rel = fp.name if p.is_file() else str(fp.relative_to(p))
        try:
            txt = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        info = introspect_webapp_source(txt, app_name)
        routes = info["sample_input"].get("routes_discovered", [])
        funcs = info["sample_input"].get("functions_extracted", [])
        file_summaries.append({
            "file": rel,
            "size_bytes": len(txt),
            "routes_count": len(routes),
            "functions_count": len(funcs),
            "routes": routes[:10],
            "functions": funcs[:10],
        })
        combined_chunks.append(f"# === FILE: {rel} ===\n{txt[:12000]}")

    combined_source = "\n\n".join(combined_chunks)
    slug = normalize_slug(f"{app_name}-skill")
    merged_introspection = introspect_webapp_source(combined_source, slug)

    return {
        "app_name": app_name,
        "skill_slug": slug,
        "source_path": str(p),
        "files_scanned": len(file_summaries),
        "file_summaries": file_summaries,
        "routes_discovered": merged_introspection["sample_input"].get("routes_discovered", []),
        "functions_extracted": merged_introspection["sample_input"].get("functions_extracted", []),
        "tools_discovered": merged_introspection.get("tools", []),
        "combined_source": combined_source[:35000],
    }


def save_skill_to_workspace(compiled: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a compiled multi-tool skill into `skills_workspace/<skill-slug>/` so the
    Plug-and-Play MCP Hub Server immediately exposes all of its tools, resources, and prompts.
    """
    SKILLS_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    spec = compiled["spec"]
    slug = normalize_slug(spec["name"])
    skill_dir = SKILLS_WORKSPACE_DIR / slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in compiled["artifacts"].items():
        target_file = skill_dir / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        if rel_path.endswith(".py"):
            try:
                target_file.chmod(0o755)
            except OSError:
                pass

    manifest = {
        "id": slug,
        "name": slug,
        "title": spec.get("title", slug),
        "category": spec.get("category", "Application Skill"),
        "version": spec.get("version", "1.0.0"),
        "description": spec.get("description", ""),
        "input_type": spec.get("input_type", "custom_workload_bundle"),
        "frameworks": spec.get("frameworks", ["Open Agent SKILL.md", "MCP JSON-RPC 2.0"]),
        "cli_flags": spec.get("cli_flags", ["--input-file", "--out-dir", "--verify-determinism"]),
        "package_sha256": compiled.get("package_sha256", ""),
        "tools": spec.get("tools", []),
        "rules": spec.get("rules", []),
        "sample_input": spec.get("sample_input", {}),
        "all_gates_passed": compiled.get("all_gates_passed", True),
    }
    (skill_dir / "skill_manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    return manifest


def list_workspace_skills() -> List[Dict[str, Any]]:
    """List all user-compiled skills currently installed in `skills_workspace/`."""
    if not SKILLS_WORKSPACE_DIR.exists():
        return []
    skills: List[Dict[str, Any]] = []
    for child in sorted(SKILLS_WORKSPACE_DIR.iterdir()):
        manifest_path = child / "skill_manifest.json"
        if child.is_dir() and manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                data["skill_dir"] = str(child)
                skills.append(data)
            except Exception:
                continue
    return skills


def delete_workspace_skill(skill_slug: str) -> bool:
    """Remove an installed skill from `skills_workspace/`."""
    import shutil
    slug = normalize_slug(skill_slug)
    target = SKILLS_WORKSPACE_DIR / slug
    if target.exists() and target.is_dir():
        shutil.rmtree(target)
        return True
    return False


def get_mcp_client_configs(server_port: int = 8108) -> Dict[str, Any]:
    """Generate plug-and-play MCP client configuration snippets for Claude Desktop, Cursor,
    Windsurf, VS Code / Cline, and HTTP JSON-RPC clients using portable paths.
    """
    stdio_entry = {
        "command": "python3",
        "args": ["./mcp_server.py"],
        "env": {
            "SKILLFORGE_WORKSPACE": "./skills_workspace",
        },
    }
    return {
        "mcp_server_script": "./mcp_server.py",
        "skills_workspace_dir": "./skills_workspace",
        "http_jsonrpc_endpoint": f"http://127.0.0.1:{server_port}/api/mcp/rpc",
        "claude_desktop_config": {
            "mcpServers": {
                "skillforge-multi-skill-hub": stdio_entry,
            }
        },
        "cursor_mcp_config": {
            "mcpServers": {
                "skillforge-multi-skill-hub": stdio_entry,
            }
        },
        "windsurf_mcp_config": {
            "mcpServers": {
                "skillforge-multi-skill-hub": stdio_entry,
            }
        },
        "vscode_cline_config": {
            "mcpServers": {
                "skillforge-multi-skill-hub": {
                    **stdio_entry,
                    "disabled": False,
                    "alwaysAllow": [],
                }
            }
        },
    }
