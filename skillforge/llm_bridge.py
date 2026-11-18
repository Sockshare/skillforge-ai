"""Multi-LLM Connection Manager & Translation Bridge for SkillForge AI.

Supports multiple simultaneous LLM configurations:
  - Local Ollama instances (e.g., http://127.0.0.1:11434 with multiple models)
  - Local OpenAI-compatible servers (LM Studio :1234, vLLM :8000, llama.cpp :8080)
  - Cloud LLM APIs (OpenAI, Anthropic, Google Gemini, OpenRouter)
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

DEFAULT_TRANSFORMATION_DOC = """# Web-App-to-LLM-Skill Transformation Guide & Specification (v2.0)

## 1. Purpose
Transform any selected **Application** (Python, FastAPI, Flask, Django, Node/Express, TypeScript, React/HTML, or OpenAPI service) into a portable, deterministic **Multi-Tool Agent Skill** and **Model Context Protocol (MCP)** package:
1. `SKILL.md` — YAML frontmatter (`name`, `description`) + when-to-use triggers + multi-tool catalog + step-by-step execution workflow + guardrails.
2. `mcp_server.py` — Plug-and-Play Model Context Protocol (`JSON-RPC 2.0`, protocol `2024-11-05`) server exposing **all discovered routes and functions as distinct MCP tools**, plus MCP `resources` (`SKILL.md`, `schema.json`) and MCP `prompts`.
3. `scripts/engine.py` — Standalone deterministic Python CLI engine supporting `--tool <tool_name>`, `--input-file <json>`, `--out-dir <dir>` (generating `Canonical_Reviewed_Dataset.json`, `<skill>_Report.md`, `<skill>_Results.csv`, and `Executive_Summary.html`), and `--verify-determinism` (proving `SHA-256 Run 1 == Run 2 == Run 3`).
4. `references/schema.json` — Multi-tool JSON Schema Draft 2020-12 contract.
5. `tests/test_skill.py` — Automated unit and 3-run `SHA-256` determinism test suite.

## 2. Transformation Rules for the LLM
- **Rule 1 (Multi-Tool Extraction):** Map every discovered HTTP endpoint (`GET`, `POST`, `PUT`, `DELETE`) and core domain function (`def ...` / `function ...`) into its own named, typed MCP tool so an LLM agent can invoke individual actions or run the full suite.
- **Rule 2 (YAML Frontmatter):** `name` must be `kebab-case` (max 64 chars). `description` must clearly state *what* the application does and *when* an LLM should invoke this skill.
- **Rule 3 (Deterministic Execution):** All tool outputs must be canonically sorted (`json.dumps(..., sort_keys=True)`) and signed with a `SHA-256` digest so 3 consecutive runs produce identical hashes.
- **Rule 4 (Safety & Guardrails):** Default to read-only inspection; require explicit user confirmation before executing mutating or destructive operations.
"""


# In-memory registry of user-added or live-discovered LLM profiles (zero hardcoded fake models)
LLM_PROFILES: Dict[str, Dict[str, Any]] = {}

# Session-only API keys (never serialized to disk)
_SESSION_API_KEYS: Dict[str, str] = {}


def get_ollama_status(ollama_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    """Probe http://127.0.0.1:11434/api/tags live and register only actually installed Ollama models."""
    base = ollama_url.rstrip("/")
    # Remove any stale auto-detected ollama-* profiles before re-probing live
    for k in [k for k, v in LLM_PROFILES.items() if v.get("auto_detected_ollama")]:
        LLM_PROFILES.pop(k, None)

    try:
        req = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "SkillForge-AI/2.0"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models: List[str] = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            for idx, mname in enumerate(models):
                pid = f"ollama-{re.sub(r'[^a-z0-9]+', '-', mname.lower()).strip('-')}"
                LLM_PROFILES[pid] = {
                    "id": pid,
                    "name": f"Local Ollama — {mname}",
                    "provider": "ollama",
                    "base_url": base,
                    "model": mname,
                    "role": "Live Local Ollama Model",
                    "temperature": 0.0,
                    "num_ctx": 2048,
                    "has_api_key": False,
                    "auto_detected_ollama": True,
                }
            return {
                "connected": len(models) > 0,
                "provider": "ollama_local",
                "endpoint": base,
                "models": models,
                "recommended_model": "llama3.2:3b" if "llama3.2:3b" in models else (models[0] if models else ""),
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": False,
            "provider": "ollama_local",
            "endpoint": base,
            "models": [],
            "error": str(exc),
        }


def list_llm_profiles() -> List[Dict[str, Any]]:
    """Return only live-verified Ollama models and user-saved LLM profiles."""
    get_ollama_status()
    out = []
    for pid, prof in LLM_PROFILES.items():
        copy_prof = dict(prof)
        copy_prof["has_api_key"] = bool(_SESSION_API_KEYS.get(pid))
        out.append(copy_prof)
    return out


def upsert_llm_profile(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """Add or update an LLM configuration profile in memory."""
    raw_id = profile_data.get("id") or profile_data.get("name") or f"llm-{int(time.time())}"
    pid = re.sub(r"[^a-z0-9\-]+", "-", str(raw_id).lower()).strip("-") or "custom-llm"
    api_key = (profile_data.get("api_key") or "").strip()
    if api_key:
        _SESSION_API_KEYS[pid] = api_key

    prof = {
        "id": pid,
        "name": profile_data.get("name") or f"{profile_data.get('provider', 'ollama').upper()} ({profile_data.get('model', 'default')})",
        "provider": (profile_data.get("provider") or "ollama").lower(),
        "base_url": (profile_data.get("base_url") or "http://127.0.0.1:11434").rstrip("/"),
        "model": profile_data.get("model") or "llama3.2:3b",
        "role": profile_data.get("role") or "Skill Translator LLM",
        "temperature": float(profile_data.get("temperature", 0.0)),
        "num_ctx": int(profile_data.get("num_ctx", 2048)),
        "has_api_key": bool(_SESSION_API_KEYS.get(pid)),
    }
    LLM_PROFILES[pid] = prof
    return prof


def delete_llm_profile(profile_id: str) -> bool:
    """Remove an LLM profile from memory."""
    _SESSION_API_KEYS.pop(profile_id, None)
    return LLM_PROFILES.pop(profile_id, None) is not None


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Extract the first valid JSON object from an LLM response string."""
    cleaned = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        brace = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if brace:
            cleaned = brace.group(1)
    return json.loads(cleaned)


def translate_webapp_with_llm(
    webapp_source: str,
    transformation_doc: str,
    llm_config: Dict[str, Any],
    app_hint_name: str = "custom-webapp-skill",
) -> Dict[str, Any]:
    """Use the selected LLM profile (Local Ollama, LM Studio/vLLM, OpenAI, Anthropic, or Gemini)
    to translate an Application + Transformation Documentation into a Multi-Tool Skill specification.
    """
    from skillforge.compiler import introspect_webapp_source

    profile_id = llm_config.get("profile_id")
    if profile_id and profile_id in LLM_PROFILES:
        prof = dict(LLM_PROFILES[profile_id])
        prof.update({k: v for k, v in llm_config.items() if v not in (None, "")})
        if not prof.get("api_key") and profile_id in _SESSION_API_KEYS:
            prof["api_key"] = _SESSION_API_KEYS[profile_id]
        llm_config = prof

    provider = (llm_config.get("provider") or "ollama").lower()
    model = llm_config.get("model") or "llama3.2:3b"
    doc_text = (transformation_doc or DEFAULT_TRANSFORMATION_DOC).strip()

    introspected = introspect_webapp_source(webapp_source, app_hint_name)
    routes_summary = ", ".join(introspected["sample_input"].get("routes_discovered", [])[:10])
    funcs_summary = ", ".join(introspected["sample_input"].get("functions_extracted", [])[:10])
    tools_count = len(introspected.get("tools", []))

    system_prompt = (
        "You are SkillForge AI. Convert the application routes and functions into a specific JSON skill definition "
        "following the user's Transformation Guide. Do NOT use placeholder strings. Return JSON only."
    )
    user_prompt = (
        f"Transformation Guide Rules: {doc_text[:380]}\n"
        f"Application Hint Name: {app_hint_name}\n"
        f"Discovered HTTP Routes: {routes_summary or 'None (CLI/Module App)'}\n"
        f"Extracted Functions/Classes ({tools_count} tools): {funcs_summary}\n"
        f"Code Header: {webapp_source[:300]}\n"
        "Respond with JSON containing keys: name, title, category, description."
    )

    content = ""
    base_url = (llm_config.get("base_url") or "http://127.0.0.1:11434").rstrip("/")

    if provider in ("ollama", "ollama_local"):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": float(llm_config.get("temperature", 0.0)),
                "seed": 42,
                "num_predict": 140,
                "num_ctx": int(llm_config.get("num_ctx", 1024)),
            },
        }
        req = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=35) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = (body.get("message") or {}).get("content") or ""

    elif provider in ("openai", "openrouter", "custom_openai"):
        api_key = (llm_config.get("api_key") or "").strip()
        if provider != "custom_openai" and not api_key:
            raise ValueError("API key is required for OpenAI / OpenRouter provider.")
        if "11434" in base_url:
            base_url = "https://api.openai.com/v1" if provider == "openai" else "http://127.0.0.1:1234/v1"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": float(llm_config.get("temperature", 0.0)),
        }
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        api_key = (llm_config.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("API key is required for Anthropic Claude provider.")
        payload = {
            "model": model or "claude-3-7-sonnet-latest",
            "max_tokens": 300,
            "temperature": 0.0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["content"][0]["text"]

    elif provider == "gemini":
        api_key = (llm_config.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("API key is required for Gemini API provider.")
        gem_model = model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["candidates"][0]["content"]["parts"][0]["text"]
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    parsed = _extract_json_object(content)
    desc = (parsed.get("description") or "").strip()
    if not desc or "when and how" in desc.lower() or len(desc) < 25:
        parsed["description"] = (
            f"Multi-tool LLM Agent Skill wrapping {tools_count} application tools "
            f"(routes: {routes_summary or 'direct CLI'}; functions: {funcs_summary or 'main'}) "
            "with deterministic JSON/Markdown/CSV/HTML reporting and 3-run SHA-256 verification."
        )
    if parsed.get("name") in (None, "", "web-app-name", "kebab-case-name", "get-health"):
        parsed["name"] = app_hint_name
    parsed["rules"] = introspected["rules"]
    parsed["tools"] = introspected["tools"]
    parsed["sample_input"] = introspected["sample_input"]
    return {
        "ok": True,
        "provider": provider,
        "model": model,
        "endpoint": base_url,
        "spec_override": parsed,
        "raw_llm_response": content,
    }
