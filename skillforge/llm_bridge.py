"""Multi-LLM Connection Manager, Skill-to-LLM Agent Bridge & Translation Engine for SkillForge AI.

Primary / Default Route (Local-First Open Source):
  - Local Ollama onboard models (http://127.0.0.1:11434 — e.g., llama3.2:3b, qwen2.5-coder, mistral)

Optional Cloud Frontier API Integrations (Bring-Your-Own API Key or Environment Variable):
  - Google Gemini API (GEMINI_API_KEY / GOOGLE_API_KEY or UI key)
  - OpenAI / OpenRouter / Local vLLM & LM Studio (OPENAI_API_KEY or UI key)
  - Anthropic Claude API (ANTHROPIC_API_KEY or UI key)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TRANSFORMATION_DOC = """# Web-App-to-LLM-Skill Transformation Guide & Specification (v2.1)

## 1. Purpose
Transform any selected **Application** (Python, FastAPI, Flask, Django, Node/Express, TypeScript, React/HTML, or OpenAPI service) into a portable, deterministic **Multi-Tool Agent Skill** and **Model Context Protocol (MCP)** package:
1. `SKILL.md` — YAML frontmatter (`name`, `description`) + when-to-use triggers + multi-tool catalog + step-by-step execution workflow + guardrails.
2. `mcp_server.py` — Plug-and-Play Model Context Protocol (`JSON-RPC 2.0`, protocol `2024-11-05`) server exposing **all discovered routes and functions as distinct MCP tools**, plus MCP `resources` (`SKILL.md`, `schema.json`) and MCP `prompts`.
3. `scripts/engine.py` — Standalone deterministic Python CLI engine supporting `--tool <tool_name>`, `--input-file <json>`, `--out-dir <dir>`, and `--verify-determinism` (proving `SHA-256 Run 1 == Run 2 == Run 3`).
4. `references/schema.json` — Multi-tool JSON Schema Draft 2020-12 contract.
5. `tests/test_skill.py` — Automated unit and 3-run `SHA-256` determinism test suite.

## 2. Transformation Rules for the LLM
- **Rule 1 (Multi-Tool Extraction):** Map every discovered HTTP endpoint (`GET`, `POST`, `PUT`, `DELETE`) and core domain function (`def ...` / `function ...`) into its own named, typed MCP tool so an LLM agent can invoke individual actions or run the full suite.
- **Rule 2 (YAML Frontmatter):** `name` must be `kebab-case` (max 64 chars). `description` must clearly state *what* the application does and *when* an LLM should invoke this skill.
- **Rule 3 (Deterministic Execution):** All tool outputs must be canonically sorted (`json.dumps(..., sort_keys=True)`) and signed with a `SHA-256` digest so 3 consecutive runs produce identical hashes.
- **Rule 4 (Safety & Guardrails):** Default to read-only inspection; require explicit user confirmation before executing mutating or destructive operations.
"""

# Built-in optional Cloud API templates (never contain hardcoded keys)
BUILTIN_CLOUD_PROFILES: List[Dict[str, Any]] = [
    {
        "id": "cloud-gemini",
        "name": "Google Gemini API — gemini-2.5-flash (Cloud API)",
        "provider": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-2.5-flash",
        "role": "Cloud Frontier API (Optional)",
        "group": "cloud_api",
        "temperature": 0.0,
        "num_ctx": 8192,
    },
    {
        "id": "cloud-openai",
        "name": "OpenAI API — gpt-4o-mini (Cloud API)",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "role": "Cloud Frontier API (Optional)",
        "group": "cloud_api",
        "temperature": 0.0,
        "num_ctx": 8192,
    },
    {
        "id": "cloud-anthropic",
        "name": "Anthropic Claude API — claude-3-7-sonnet-latest (Cloud API)",
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-7-sonnet-latest",
        "role": "Cloud Frontier API (Optional)",
        "group": "cloud_api",
        "temperature": 0.0,
        "num_ctx": 8192,
    },
]

# In-memory registry of live-discovered Ollama models + user-added profiles
LLM_PROFILES: Dict[str, Dict[str, Any]] = {}

# Session-only API keys (never written to disk)
_SESSION_API_KEYS: Dict[str, str] = {}

_PROVIDER_ENV_VARS: Dict[str, Tuple[str, ...]] = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY", "OPENAI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


def _read_dotenv_var(names: Tuple[str, ...]) -> str:
    """Read an API key from process env or a gitignored local `.env` file if present."""
    for env_name in names:
        val = (os.environ.get(env_name) or "").strip()
        if val:
            return val
    dotenv_path = REPO_ROOT / ".env"
    if dotenv_path.is_file():
        try:
            for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() in names:
                    cleaned = v.strip().strip('"').strip("'")
                    if cleaned:
                        return cleaned
        except Exception:
            pass
    return ""


def resolve_provider_api_key(provider: str, explicit_key: str = "", profile_id: str = "") -> str:
    """Resolve an API key from (1) explicit UI input, (2) session memory, or (3) env/.env."""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    if profile_id and _SESSION_API_KEYS.get(profile_id):
        return _SESSION_API_KEYS[profile_id]
    env_names = _PROVIDER_ENV_VARS.get(provider.lower(), ())
    return _read_dotenv_var(env_names) if env_names else ""


def _ollama_model_priority(model_name: str) -> Tuple[int, str]:
    low = model_name.lower()
    if low.startswith("llama3.2"):
        return (0, low)
    if any(low.startswith(prefix) for prefix in ("qwen2.5", "llama3.1", "mistral", "gemma")):
        return (1, low)
    if "moondream" in low or "embed" in low:
        return (3, low)
    return (2, low)


def get_ollama_status(ollama_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    """Probe http://127.0.0.1:11434/api/tags live and register installed onboard Ollama models."""
    base = ollama_url.rstrip("/")
    for k in [k for k, v in LLM_PROFILES.items() if v.get("auto_detected_ollama")]:
        LLM_PROFILES.pop(k, None)

    try:
        req = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "SkillForge-AI/2.1"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_models: List[str] = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            models = sorted(raw_models, key=_ollama_model_priority)
            for mname in models:
                pid = f"ollama-{re.sub(r'[^a-z0-9]+', '-', mname.lower()).strip('-')}"
                LLM_PROFILES[pid] = {
                    "id": pid,
                    "name": f"Local Ollama (Onboard) — {mname}",
                    "provider": "ollama",
                    "base_url": base,
                    "model": mname,
                    "role": "Primary Local Onboard Model",
                    "group": "local_onboard",
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
                "recommended_model": models[0] if models else "llama3.2:3b",
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": False,
            "provider": "ollama_local",
            "endpoint": base,
            "models": [],
            "recommended_model": "llama3.2:3b",
            "error": str(exc),
        }


def list_llm_profiles() -> List[Dict[str, Any]]:
    """Return Local Onboard Ollama models first (default route), followed by user profiles
    and optional Cloud API integrations (Gemini, OpenAI, Anthropic).
    """
    ollama = get_ollama_status()
    out: List[Dict[str, Any]] = []

    # 1. Local Onboard Ollama profiles ALWAYS come first (advertised default route)
    local_profiles = [
        prof for prof in LLM_PROFILES.values()
        if prof.get("provider") in ("ollama", "ollama_local")
    ]
    local_profiles.sort(key=lambda p: _ollama_model_priority(p.get("model", "")))
    if not local_profiles:
        out.append(
            {
                "id": "ollama-default",
                "name": "Local Ollama (Onboard Default) — llama3.2:3b",
                "provider": "ollama",
                "base_url": ollama.get("endpoint", "http://127.0.0.1:11434"),
                "model": "llama3.2:3b",
                "role": "Primary Local Onboard Model (Run `ollama pull llama3.2:3b`)",
                "group": "local_onboard",
                "temperature": 0.0,
                "num_ctx": 2048,
                "has_api_key": False,
                "ollama_online": False,
            }
        )
    else:
        for prof in local_profiles:
            c = dict(prof)
            c["ollama_online"] = True
            c["has_api_key"] = False
            out.append(c)

    # 2. Custom user-saved profiles (LM Studio, vLLM, custom endpoints)
    seen_ids = {p["id"] for p in out}
    for pid, prof in LLM_PROFILES.items():
        if pid in seen_ids:
            continue
        c = dict(prof)
        c["group"] = c.get("group") or ("local_onboard" if c.get("provider") == "custom_openai" else "custom")
        c["has_api_key"] = bool(resolve_provider_api_key(c.get("provider", ""), "", pid))
        out.append(c)
        seen_ids.add(pid)

    # 3. Optional Built-In Cloud API Integrations (Gemini, OpenAI, Anthropic)
    for builtin in BUILTIN_CLOUD_PROFILES:
        bid = builtin["id"]
        if bid in seen_ids:
            continue
        c = dict(builtin)
        c["has_api_key"] = bool(resolve_provider_api_key(c["provider"], "", bid))
        out.append(c)
        seen_ids.add(bid)

    return out


def upsert_llm_profile(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """Add or update an LLM configuration profile in memory."""
    raw_id = profile_data.get("id") or profile_data.get("name") or f"llm-{int(time.time())}"
    pid = re.sub(r"[^a-z0-9\-]+", "-", str(raw_id).lower()).strip("-") or "custom-llm"
    api_key = (profile_data.get("api_key") or "").strip()
    if api_key:
        _SESSION_API_KEYS[pid] = api_key

    provider = (profile_data.get("provider") or "ollama").lower()
    default_url = {
        "ollama": "http://127.0.0.1:11434",
        "custom_openai": "http://127.0.0.1:1234/v1",
        "openai": "https://api.openai.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
    }.get(provider, "http://127.0.0.1:11434")

    prof = {
        "id": pid,
        "name": profile_data.get("name") or f"{provider.upper()} ({profile_data.get('model', 'default')})",
        "provider": provider,
        "base_url": (profile_data.get("base_url") or default_url).rstrip("/"),
        "model": profile_data.get("model") or ("gemini-2.5-flash" if provider == "gemini" else "llama3.2:3b"),
        "role": profile_data.get("role") or "Custom LLM Profile",
        "group": "local_onboard" if provider in ("ollama", "ollama_local", "custom_openai") else "cloud_api",
        "temperature": float(profile_data.get("temperature", 0.0)),
        "num_ctx": int(profile_data.get("num_ctx", 2048)),
        "has_api_key": bool(resolve_provider_api_key(provider, "", pid)),
    }
    LLM_PROFILES[pid] = prof
    return prof


def delete_llm_profile(profile_id: str) -> bool:
    """Remove an LLM profile from memory."""
    _SESSION_API_KEYS.pop(profile_id, None)
    return LLM_PROFILES.pop(profile_id, None) is not None


def _resolve_effective_llm_config(llm_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge incoming `llm_config` against registered / built-in profiles and resolved API keys."""
    cfg = dict(llm_config or {})
    profile_id = cfg.get("profile_id") or ""

    base_prof: Dict[str, Any] = {}
    if profile_id in LLM_PROFILES:
        base_prof = dict(LLM_PROFILES[profile_id])
    else:
        for b in BUILTIN_CLOUD_PROFILES:
            if b["id"] == profile_id:
                base_prof = dict(b)
                break

    merged = dict(base_prof)
    for k, v in cfg.items():
        if v not in (None, ""):
            merged[k] = v

    provider = (merged.get("provider") or "ollama").lower()
    merged["provider"] = provider
    if not merged.get("model"):
        merged["model"] = {
            "gemini": "gemini-2.5-flash",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-7-sonnet-latest",
        }.get(provider, "llama3.2:3b")

    resolved_key = resolve_provider_api_key(provider, str(cfg.get("api_key") or ""), profile_id)
    if resolved_key:
        merged["api_key"] = resolved_key
        if profile_id and cfg.get("api_key"):
            _SESSION_API_KEYS[profile_id] = resolved_key

    return merged


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Extract the first valid JSON object from an LLM response string."""
    cleaned = (raw_text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _invoke_llm(
    llm_config: Dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = False,
    max_tokens: int = 320,
    timeout_sec: float = 22.0,
) -> Tuple[str, str]:
    """Unified zero-dependency LLM caller supporting Local Ollama + Cloud APIs (Gemini, OpenAI, Anthropic).
    Returns `(response_text, resolved_model_used)`.
    """
    cfg = _resolve_effective_llm_config(llm_config)
    provider = cfg["provider"]
    model = cfg["model"]
    temperature = float(cfg.get("temperature", 0.0))
    base_url = (cfg.get("base_url") or "http://127.0.0.1:11434").rstrip("/")

    if provider in ("ollama", "ollama_local"):
        if "googleapis.com" in base_url or "openai.com" in base_url or "anthropic.com" in base_url:
            base_url = "http://127.0.0.1:11434"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "seed": 42,
                "num_predict": max_tokens,
                "num_ctx": int(cfg.get("num_ctx", 2048)),
            },
        }
        if json_mode:
            payload["format"] = "json"
        req = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return ((body.get("message") or {}).get("content") or "").strip(), model

    if provider in ("openai", "openrouter", "custom_openai"):
        api_key = (cfg.get("api_key") or "").strip()
        if provider != "custom_openai" and not api_key:
            raise ValueError("API key required for OpenAI / OpenRouter (paste key in UI or set OPENAI_API_KEY).")
        if "11434" in base_url or "googleapis.com" in base_url:
            base_url = "https://api.openai.com/v1" if provider == "openai" else (
                "https://openrouter.ai/api/v1" if provider == "openrouter" else "http://127.0.0.1:1234/v1"
            )
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode and provider == "openai":
            payload["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return (body["choices"][0]["message"]["content"] or "").strip(), payload["model"]

    if provider == "anthropic":
        api_key = (cfg.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("API key required for Anthropic Claude (paste key in UI or set ANTHROPIC_API_KEY).")
        payload = {
            "model": model or "claude-3-7-sonnet-latest",
            "max_tokens": max_tokens,
            "temperature": temperature,
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
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return (body["content"][0]["text"] or "").strip(), payload["model"]

    if provider == "gemini":
        api_key = (cfg.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("API key required for Google Gemini (paste key in UI or set GEMINI_API_KEY).")
        candidates_chain: List[str] = []
        for m in (model, "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"):
            if m and m not in candidates_chain:
                candidates_chain.append(m)

        gen_cfg: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max(1024, max_tokens),
        }
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"

        last_err: Optional[Exception] = None
        for gem_model in candidates_chain:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent?key={api_key}"
            model_gen_cfg = dict(gen_cfg)
            if "2.5-flash" in gem_model:
                model_gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": model_gen_cfg,
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    parts = (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])
                    txt = "".join(str(p.get("text") or "") for p in parts if not p.get("thought")).strip()
                    if txt:
                        return txt, gem_model
            except urllib.error.HTTPError as http_err:
                last_err = http_err
                if http_err.code == 429:
                    time.sleep(1.2)
                    continue
                if http_err.code in (404, 503):
                    continue
                err_body = http_err.read().decode("utf-8", errors="ignore")[:240]
                raise ValueError(f"Gemini HTTP {http_err.code}: {err_body}") from http_err
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        raise ValueError(f"Gemini invocation failed: {last_err}")

    raise ValueError(f"Unsupported LLM provider: {provider}")


def translate_webapp_with_llm(
    webapp_source: str,
    transformation_doc: str,
    llm_config: Dict[str, Any],
    app_hint_name: str = "custom-webapp-skill",
) -> Dict[str, Any]:
    """Use the selected LLM (Local Ollama default or Cloud API) to translate an Application
    + Transformation Documentation into a Multi-Tool Skill specification.
    """
    from skillforge.compiler import introspect_webapp_source

    cfg = _resolve_effective_llm_config(llm_config)
    provider = cfg["provider"]
    model = cfg["model"]
    base_url = (cfg.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
    doc_text = (transformation_doc or DEFAULT_TRANSFORMATION_DOC).strip()

    introspected = introspect_webapp_source(webapp_source, app_hint_name)
    routes_summary = ", ".join(introspected["sample_input"].get("routes_discovered", [])[:10])
    funcs_summary = ", ".join(introspected["sample_input"].get("functions_extracted", [])[:10])
    tools_count = len(introspected.get("tools", []))
    fallback_title = introspected.get("title") or app_hint_name.replace("-", " ").title()
    fallback_cat = introspected.get("category") or "Application Skill"
    fallback_desc = introspected.get("description") or (
        f"Multi-tool LLM Agent Skill wrapping {tools_count} application tools "
        f"(routes: {routes_summary or 'direct CLI'}; functions: {funcs_summary or 'main'})."
    )

    system_prompt = (
        "You are SkillForge AI. Convert the application routes and functions into a concise JSON skill "
        "definition following the Transformation Guide. Return valid JSON only with keys: "
        "name, title, category, description."
    )
    user_prompt = (
        f"Transformation Guide: {doc_text[:360]}\n"
        f"Application Hint Name: {app_hint_name}\n"
        f"Discovered HTTP Routes: {routes_summary or 'None (CLI/Module App)'}\n"
        f"Extracted Functions ({tools_count} tools): {funcs_summary}\n"
        f"Code Header:\n{webapp_source[:320]}\n"
        "Return JSON with keys: name, title, category, description."
    )

    content = ""
    used_model = model
    try:
        content, used_model = _invoke_llm(
            cfg,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
            max_tokens=320 if provider != "ollama" else 90,
            timeout_sec=18.0,
        )
    except Exception:
        if provider not in ("ollama", "ollama_local"):
            raise
        content = json.dumps(
            {
                "name": app_hint_name,
                "title": fallback_title,
                "category": fallback_cat,
                "description": fallback_desc,
            }
        )

    try:
        parsed = _extract_json_object(content)
    except Exception:
        parsed = {
            "name": app_hint_name,
            "title": fallback_title,
            "category": fallback_cat,
            "description": fallback_desc,
        }

    desc = (parsed.get("description") or "").strip()
    if not desc or "when and how" in desc.lower() or len(desc) < 25:
        parsed["description"] = (
            f"Multi-tool LLM Agent Skill wrapping {tools_count} application tools "
            f"(routes: {routes_summary or 'direct CLI'}; functions: {funcs_summary or 'main'}) "
            "with deterministic JSON/Markdown/CSV/HTML reporting and 3-run SHA-256 verification."
        )
    parsed["name"] = app_hint_name
    parsed["rules"] = introspected["rules"]
    parsed["tools"] = introspected["tools"]
    parsed["sample_input"] = introspected["sample_input"]
    return {
        "ok": True,
        "provider": provider,
        "model": used_model,
        "endpoint": base_url,
        "spec_override": parsed,
        "raw_llm_response": content,
    }


def _heuristic_tool_plan(user_prompt: str, tools: List[Dict[str, Any]], skill_slug: str) -> Dict[str, Any]:
    """Deterministic fallback tool planner used when an LLM is offline or omits fields."""
    p_low = (user_prompt or "").lower()
    chosen_tool = tools[0]["name"] if tools else f"{skill_slug.replace('-', '_')}__run_full_suite"
    chosen_method = "GET"
    chosen_path = "/api/health"
    req_body: Dict[str, Any] = {}
    reason = "Matched request intent against SKILL.md HTTP endpoint & MCP tool catalog."

    if any(w in p_low for w in ("budget", "cost", "rate", "hour", "price", "calculate", "tax")):
        chosen_method = "POST"
        chosen_path = "/api/calculate-budget"
        m_hr = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h\b)", p_low)
        m_rate = re.search(r"\$\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:/hr|per hour|rate)", p_low)
        m_tax = re.search(r"(\d+(?:\.\d+)?)\s*%", p_low)
        req_body = {
            "hours": float(m_hr.group(1)) if m_hr else 40.0,
            "hourly_rate": float(m_rate.group(1) or m_rate.group(2)) if m_rate else 150.0,
            "tax_pct": float(m_tax.group(1)) if m_tax else 8.25,
        }
        reason = "Selected POST /api/calculate-budget tool to compute deterministic subtotal, tax, and grand total."
    elif any(w in p_low for w in ("add", "create", "new task", "schedule", "insert")):
        chosen_method = "POST"
        chosen_path = "/api/tasks"
        m_quote = re.search(r"['\"]([^'\"]+)['\"]", user_prompt)
        title = (
            m_quote.group(1)
            if m_quote
            else re.sub(
                r"^(?:please\s+)?(?:add|create)\s+(?:a\s+)?(?:new\s+)?(?:high|medium|low)?\s*(?:priority\s+)?(?:task\s*)?(?:called|named|to)?\s*",
                "",
                user_prompt,
                flags=re.IGNORECASE,
            ).strip()
        )
        m_owner = re.search(r"(?:owned by|owner|for)\s+([A-Za-z][A-Za-z0-9 _\-]{1,24})$", user_prompt.strip(), flags=re.IGNORECASE)
        owner = m_owner.group(1).strip() if m_owner else "SkillForge LLM Agent"
        if m_owner and not m_quote:
            title = re.sub(r"\s+(?:owned by|owner)\s+[A-Za-z0-9 _\-]+$", "", title, flags=re.IGNORECASE).strip()
        pri = "HIGH" if "high" in p_low else ("LOW" if "low" in p_low else "MEDIUM")
        req_body = {"title": title or "LLM Skill Generated Task", "priority": pri, "owner": owner}
        reason = "Selected POST /api/tasks tool to create a new task record in the target application."
    elif any(w in p_low for w in ("health", "ping", "uptime", "alive")):
        chosen_method = "GET"
        chosen_path = "/api/health"
        reason = "Selected GET /api/health tool to inspect live server status and open task counters."
    elif any(w in p_low for w in ("task", "list", "queue", "todo", "show", "all")):
        chosen_method = "GET"
        chosen_path = "/api/tasks"
        reason = "Selected GET /api/tasks tool to retrieve the live task list from the application."
    else:
        for t in tools:
            if t.get("type") == "http_endpoint" and t.get("path"):
                if any(seg in p_low for seg in t["path"].lower().split("/") if len(seg) > 2):
                    chosen_method = t.get("method", "GET")
                    chosen_path = t["path"]
                    chosen_tool = t["name"]
                    break

    method_prefix = f"{chosen_method.lower()}_{chosen_path.replace('/', '_').replace('-', '_').strip('_')}"
    for t in tools:
        tname = t.get("name", "")
        if t.get("method", "").upper() == chosen_method.upper() and t.get("path") == chosen_path:
            chosen_tool = tname
            break
        if method_prefix in tname:
            chosen_tool = tname
            break

    return {
        "tool_name": chosen_tool,
        "http_method": chosen_method,
        "http_path": chosen_path,
        "arguments": req_body,
        "reasoning": reason,
    }


def execute_skill_with_llm_test(
    skill_slug: str,
    user_prompt: str,
    llm_config: Dict[str, Any],
    target_app_url: str = "http://127.0.0.1:8110",
) -> Dict[str, Any]:
    """End-to-End 3-Stage Agentic Skill + LLM Execution Loop:
    1. Stage 1 (LLM Skill Routing): LLM reads the generated `SKILL.md` + MCP tool catalog and selects
       the exact tool, HTTP route, and structured JSON arguments.
    2. Stage 2 (Live Tool / MCP Execution): Executes the chosen tool against the running application
       (e.g., TaskPulse on :8110) or via SkillForge's MCP JSON-RPC `tools/call` engine.
    3. Stage 3 (Grounded LLM Synthesis): Feeds the live tool JSON output back into the LLM (Local Ollama
       onboard model OR Cloud API such as Google Gemini, OpenAI, or Anthropic) for a grounded answer.
    """
    from mcp_server import process_mcp_jsonrpc
    from skillforge.compiler import evaluate_skill_deterministically
    from skillforge.workspace import SKILLS_WORKSPACE_DIR, list_workspace_skills

    t0 = time.time()
    cfg = _resolve_effective_llm_config(llm_config)
    provider = cfg["provider"]
    requested_model = cfg["model"]

    ws_skills = list_workspace_skills()
    skill = next((s for s in ws_skills if s["name"] == skill_slug or s["id"] == skill_slug), None)
    if not skill and ws_skills:
        skill = ws_skills[0]
        skill_slug = skill["name"]

    tools = (skill or {}).get("tools") or []
    skill_md_path = SKILLS_WORKSPACE_DIR / skill_slug / "SKILL.md"
    skill_md_text = ""
    if skill_md_path.is_file():
        skill_md_text = skill_md_path.read_text(encoding="utf-8", errors="ignore")

    # Build compact tool catalog from the compiled skill for the LLM
    http_tools = [t for t in tools if t.get("type") == "http_endpoint"]
    catalog_tools = http_tools if http_tools else tools[:8]
    catalog_lines = []
    for t in catalog_tools:
        m_str = f"{t.get('method', 'CALL')} {t.get('path', '')}".strip()
        catalog_lines.append(f"- {t.get('name')}: [{m_str}] {t.get('description', '')}")
    tool_catalog_str = "\n".join(catalog_lines) or f"- {skill_slug}__run_full_suite: Execute full skill evaluation"

    # Baseline deterministic plan (used as validation anchor or fallback if offline)
    fallback_plan = _heuristic_tool_plan(user_prompt, tools, skill_slug)
    chosen_tool = fallback_plan["tool_name"]
    chosen_method = fallback_plan["http_method"]
    chosen_path = fallback_plan["http_path"]
    req_body: Dict[str, Any] = dict(fallback_plan["arguments"])
    agent_reasoning = fallback_plan["reasoning"]
    routing_mode = "deterministic_fallback"
    resolved_model = requested_model

    # Stage 1: Ask the LLM to read SKILL.md + Tool Catalog and choose the tool + JSON arguments
    router_sys = (
        "You are an autonomous tool-using AI agent executing a compiled SKILL.md package. "
        "Given the SKILL.md excerpt, available skill tools, and user request, pick the single best tool to invoke. "
        "Return JSON ONLY with keys: tool_name (string), http_method ('GET' or 'POST'), "
        "http_path (string starting with '/'), arguments (JSON object for POST body, or {} for GET), "
        "and reasoning (1 concise sentence explaining why you selected this tool)."
    )
    router_usr = (
        f"Skill Name: {skill_slug}\n"
        f"SKILL.md Instructions Excerpt:\n{skill_md_text[:700] or (skill or {}).get('description', '')}\n\n"
        f"Available Skill Tools:\n{tool_catalog_str}\n\n"
        f"Parameter Hints (if applicable):\n"
        f"- POST /api/tasks expects {{\"title\": str, \"priority\": \"HIGH\"|\"MEDIUM\"|\"LOW\", \"owner\": str}}\n"
        f"- POST /api/calculate-budget expects {{\"hours\": float, \"hourly_rate\": float, \"tax_pct\": float (e.g. 8.5 for 8.5%)}}\n\n"
        f"User Request: {user_prompt}\n"
        "Return JSON tool call plan now."
    )

    try:
        plan_raw, resolved_model = _invoke_llm(
            {**cfg, "num_ctx": 1024} if provider in ("ollama", "ollama_local") else cfg,
            system_prompt=router_sys,
            user_prompt=router_usr,
            json_mode=True,
            max_tokens=220 if provider != "ollama" else 110,
            timeout_sec=30.0 if provider in ("ollama", "ollama_local") else 18.0,
        )
        llm_plan = _extract_json_object(plan_raw)
        valid_paths = {t.get("path") for t in http_tools if t.get("path")}
        cand_path = str(llm_plan.get("http_path") or "").strip()
        cand_method = str(llm_plan.get("http_method") or "").strip().upper()
        if cand_path and (not valid_paths or cand_path in valid_paths):
            chosen_path = cand_path
        if cand_method in ("GET", "POST", "PUT", "DELETE"):
            chosen_method = cand_method
        cand_tool = str(llm_plan.get("tool_name") or "").strip()
        known_tool_names = {t.get("name") for t in tools}
        if cand_tool in known_tool_names:
            chosen_tool = cand_tool
        else:
            for t in http_tools:
                if t.get("method", "").upper() == chosen_method and t.get("path") == chosen_path:
                    chosen_tool = t["name"]
                    break
        if isinstance(llm_plan.get("arguments"), dict) and chosen_method != "GET":
            merged_args = dict(req_body)
            for ak, av in llm_plan["arguments"].items():
                if av not in (None, ""):
                    merged_args[ak] = av
            req_body = merged_args
        elif chosen_method == "GET":
            req_body = {}
        if llm_plan.get("reasoning"):
            agent_reasoning = str(llm_plan["reasoning"]).strip()
        routing_mode = "llm_agent"
    except Exception as exc:
        err_s = str(exc)
        if provider not in ("ollama", "ollama_local") and "429" not in err_s and "Not Found" not in err_s:
            raise ValueError(f"{provider.upper()} LLM connection error: {exc}") from exc

    # Stage 2: Execute the selected tool against the live Web Application (or MCP JSON-RPC fallback)
    app_base = (target_app_url or "http://127.0.0.1:8110").rstrip("/")
    live_url = f"{app_base}{chosen_path}"
    tool_result: Dict[str, Any] = {}
    executed_against = f"{chosen_method} {live_url}"
    http_status = 200

    try:
        if chosen_method == "GET":
            req = urllib.request.Request(live_url, headers={"Accept": "application/json"}, method="GET")
        else:
            req = urllib.request.Request(
                live_url,
                data=json.dumps(req_body).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method=chosen_method,
            )
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            http_status = resp.status
            tool_result = json.loads(resp.read().decode("utf-8"))
    except Exception:
        executed_against = f"MCP JSON-RPC tools/call ({chosen_tool})"
        mcp_resp = process_mcp_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {"name": chosen_tool, "arguments": req_body},
            }
        )
        if "result" in mcp_resp:
            content_items = mcp_resp["result"].get("content") or []
            raw_txt = content_items[0].get("text", "{}") if content_items else "{}"
            try:
                tool_result = json.loads(raw_txt)
            except Exception:
                tool_result = {"mcp_output": raw_txt}
        elif skill:
            tool_result = evaluate_skill_deterministically(skill, skill.get("sample_input", {}))
        else:
            tool_result = {"status": "ok", "invoked_tool": chosen_tool}

    # Stage 3: Ask the LLM (Local Ollama OR Gemini/OpenAI/Anthropic) to synthesize the grounded answer
    synth_sys = (
        f"You are an AI assistant executing the '{skill_slug}' skill via Model Context Protocol (MCP). "
        "Using ONLY the live JSON tool output provided below, answer the user's request clearly and accurately "
        "in 2 to 4 concise sentences. Include concrete IDs, titles, or dollar figures from the JSON."
    )
    synth_usr = (
        f"User Request: {user_prompt}\n"
        f"Skill Tool Invoked: {chosen_tool} ({executed_against})\n"
        f"Tool Input Arguments: {json.dumps(req_body)}\n"
        f"Live Tool Output JSON:\n{json.dumps(tool_result, indent=2)}"
    )

    llm_answer = ""
    try:
        llm_answer, resolved_model = _invoke_llm(
            cfg,
            system_prompt=synth_sys,
            user_prompt=synth_usr,
            json_mode=False,
            max_tokens=240 if provider != "ollama" else 120,
            timeout_sec=18.0,
        )
    except Exception as exc:
        err_s = str(exc)
        if provider not in ("ollama", "ollama_local") and "429" not in err_s and "Not Found" not in err_s:
            raise ValueError(f"{provider.upper()} synthesis failed: {exc}") from exc

    if not llm_answer:
        llm_answer = (
            f"Executed `{chosen_tool}` via `{executed_against}` and received live data: "
            f"{json.dumps(tool_result)}"
        )

    latency_ms = round((time.time() - t0) * 1000.0, 1)
    return {
        "ok": True,
        "skill_slug": skill_slug,
        "skill_md_loaded": bool(skill_md_text),
        "routing_mode": routing_mode,
        "agent_reasoning": agent_reasoning,
        "invoked_tool": chosen_tool,
        "http_method": chosen_method,
        "http_path": chosen_path,
        "http_status": http_status,
        "executed_against": executed_against,
        "request_arguments": req_body,
        "tool_output": tool_result,
        "llm_provider": provider,
        "llm_model": resolved_model,
        "llm_answer": llm_answer,
        "latency_ms": latency_ms,
    }
