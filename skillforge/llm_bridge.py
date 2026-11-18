"""Live LLM Translation Bridge (Local Ollama + Cloud OpenAI/Anthropic/Gemini APIs)
for translating any Web Application + Transformation Documentation into a verified LLM Skill.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List

DEFAULT_TRANSFORMATION_DOC = """# Web-App-to-LLM-Skill Transformation Guide & Specification (v1.0)

## 1. Objective
Transform the provided **Web Application** (FastAPI, Flask, Express.js, Python HTTP server, React/HTML frontend, or OpenAPI 3.1 specification) into a portable, deterministic **LLM Agent Skill Package** consisting of:
1. `SKILL.md` — YAML frontmatter (`name`, `description`) + when-to-use triggers + step-by-step LLM workflow + guardrails.
2. `mcp_server.py` — Model Context Protocol (`JSON-RPC 2.0`) tool server wrapping the web app's endpoints.
3. `scripts/engine.py` — Deterministic CLI tool that outputs canonically sorted JSON and a `SHA-256` verification digest.
4. `references/schema.json` — JSON Schema Draft 2020-12 input/output contract.
5. `tests/test_skill.py` — Automated unit and 3-run `SHA-256` determinism tests.

## 2. Mandatory Transformation Rules
- **Rule 1 (Endpoint & Action Extraction):** Identify every HTTP route (`GET`, `POST`, `PUT`, `DELETE`), query parameter, JSON body schema, and UI form action exposed by the web application.
- **Rule 2 (YAML Frontmatter):** `name` must be `kebab-case` (max 64 chars). `description` must state both *what* the web app skill does and *when* the LLM should invoke it.
- **Rule 3 (Deterministic Execution):** Never rely on free-form LLM arithmetic or unseeded randomness. Route all calculations and state checks through `scripts/engine.py` with `json.dumps(..., sort_keys=True)`.
- **Rule 4 (Safety & Guardrails):** Enforce read-only inspection by default; require explicit user confirmation before executing mutating (`POST`/`DELETE`) web app actions.

## 3. Expected JSON Output Schema from LLM Translator
Return a single JSON object with:
{
  "name": "kebab-case-skill-name",
  "title": "Human Readable Skill Title",
  "category": "Web App -> LLM Skill",
  "description": "YAML frontmatter trigger description...",
  "guardrails": ["Guardrail 1", "Guardrail 2"],
  "rules": [
    {
      "rule_id": "WEBAPP-001",
      "title": "Endpoint or workflow verification title",
      "severity": "HIGH",
      "control": "MCP Tool Bridge (POST /api/...)",
      "remediation": "Actionable remediation or usage guidance"
    }
  ]
}
"""


def get_ollama_status(ollama_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    """Check if local Ollama server is reachable and list installed local models."""
    base = ollama_url.rstrip("/")
    try:
        req = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "SkillForge-AI/1.0"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models: List[str] = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return {
                "connected": True,
                "provider": "ollama_local",
                "endpoint": base,
                "models": models,
                "recommended_model": "llama3.2:3b" if "llama3.2:3b" in models else (models[0] if models else "llama3.2:3b"),
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": False,
            "provider": "ollama_local",
            "endpoint": base,
            "models": [],
            "error": str(exc),
        }


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
) -> Dict[str, Any]:
    """Use Local Ollama or a Cloud LLM API (OpenAI / Anthropic / Gemini) to translate
    a Web Application + Transformation Documentation into a structured Skill specification.
    """
    provider = (llm_config.get("provider") or "ollama").lower()
    model = llm_config.get("model") or "llama3.2:3b"
    doc_text = (transformation_doc or DEFAULT_TRANSFORMATION_DOC).strip()

    system_prompt = (
        "You are SkillForge AI, an expert Agentic Skill Architect. "
        "Follow the user's Transformation Documentation strictly to convert the provided Web Application "
        "into a JSON skill specification. Respond ONLY with valid JSON."
    )
    user_prompt = (
        f"=== TRANSFORMATION DOCUMENTATION ===\n{doc_text[:3500]}\n\n"
        f"=== WEB APPLICATION SOURCE / ROUTES / BLUEPRINT ===\n{webapp_source[:4500]}\n\n"
        "Output ONLY a valid JSON object with keys: name, title, category, description, guardrails, rules."
    )

    if provider in ("ollama", "ollama_local"):
        base_url = (llm_config.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0, "seed": 42},
        }
        req = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = (body.get("message") or {}).get("content") or ""
            parsed = _extract_json_object(content)
            return {
                "ok": True,
                "provider": "ollama",
                "model": model,
                "endpoint": base_url,
                "spec_override": parsed,
                "raw_llm_response": content,
            }

    if provider in ("openai", "openrouter", "custom_openai"):
        api_key = (llm_config.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("API key is required for Cloud OpenAI/OpenRouter provider.")
        base_url = (llm_config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        payload = {
            "model": model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            parsed = _extract_json_object(content)
            return {
                "ok": True,
                "provider": provider,
                "model": model,
                "endpoint": base_url,
                "spec_override": parsed,
                "raw_llm_response": content,
            }

    if provider == "gemini":
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
            parsed = _extract_json_object(content)
            return {
                "ok": True,
                "provider": "gemini",
                "model": gem_model,
                "endpoint": "https://generativelanguage.googleapis.com",
                "spec_override": parsed,
                "raw_llm_response": content,
            }

    raise ValueError(f"Unsupported LLM provider: {provider}")
