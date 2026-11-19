# SkillForge AI — Web-App-to-Agent-Skill (`SKILL.md`), Deterministic CLI & MCP Compiler Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-indigo.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B%20Zero--Dependency-10b981.svg)](server.py)
[![Primary Engine: Local Ollama](https://img.shields.io/badge/Default%20LLM-Local%20Ollama%20%28Onboard%29-22c55e.svg)](#llm-engine-modes-local-ollama-default--optional-cloud-apis)
[![MCP JSON-RPC 2.0](https://img.shields.io/badge/MCP-JSON--RPC%202.0%20%282024--11--05%29-06b6d4.svg)](mcp_server.py)
[![Determinism Verified](https://img.shields.io/badge/Determinism-3--Run%20SHA--256%20Verified-f59e0b.svg)](cli.py)

**SkillForge AI** is a zero-dependency, local-first compiler studio and live agent testbench that converts any web application, **OpenAPI 3.1** service, Python/TypeScript codebase, or security/compliance blueprint into a cryptographically verified **Multi-Tool AI Agent Skill Package**:

1. **`SKILL.md`** — Open-standard Agent Skill specification with validated YAML frontmatter (`name`, `description`, `version`), multi-tool routing rules, and operational guardrails.
2. **`mcp_server.py`** — Plug-and-play **Model Context Protocol (`JSON-RPC 2.0`, `2024-11-05`)** server exposing every discovered HTTP route and function as a callable MCP tool, alongside MCP `resources` and `prompts`.
3. **`scripts/engine.py`** — Zero-dependency deterministic Python 3 CLI engine with canonical JSON key sorting and 3-run `SHA-256` output verification.
4. **`references/schema.json`** — Strict **JSON Schema Draft 2020-12** contracts plus ready-to-use adapters for **OpenAI Function Calling** and **LangGraph `StructuredTool`**.
5. **`tests/test_skill.py`** — Automated unit and 3-run `SHA-256` determinism verification test suite.

---

## LLM Engine Modes: Local Ollama Default + Optional Cloud APIs

SkillForge AI is built **local-first** so every feature runs privately on your own hardware out of the box, while also supporting optional closed-source frontier APIs whenever you want cloud-scale reasoning:

| Route | Provider(s) | Setup | Best For |
| :--- | :--- | :--- | :--- |
| **1. Local Onboard Model *(Recommended Default)*** | **Ollama** (`http://127.0.0.1:11434`) + LM Studio / vLLM | `ollama pull llama3.2:3b` *(auto-detected live via `/api/tags`)* | 100% private, air-gapped, zero-API-cost skill translation & live tool-call testing. |
| **2. Cloud Frontier APIs *(Optional Integration)*** | **Google Gemini** (`gemini-2.5-flash`), **OpenAI** (`gpt-4o-mini`), **Anthropic Claude** (`claude-3-7-sonnet-latest`), **OpenRouter** | Paste an API key in the UI or set `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` in `.env` | High-speed frontier tool routing, multi-step parameter extraction, and side-by-side model comparison. |

> **Security Note:** API keys entered in the UI are held strictly in volatile session memory and are never written to disk or exported into compiled skill bundles.

---

## Architecture & Live 3-Stage LLM ↔ Skill Testbench

```
+---------------------------------------------------------------------------------------------------+
|                                   SKILLFORGE AI STUDIO (:8108)                                    |
|                                                                                                   |
|  STEP 1: APPLICATION -> SKILL COMPILER                                                            |
|  [PC App Folder / TaskPulse :8110] -> [Route & AST Extractor] -> [5-Gate & 3x SHA-256 Verifier]   |
|                                                                          |                        |
|                                                                          v                        |
|                                                    skills_workspace/<app-skill>/                  |
|                                                    ├── SKILL.md                                   |
|                                                    ├── mcp_server.py  (JSON-RPC 2.0)              |
|                                                    ├── scripts/engine.py                          |
|                                                    └── references/schema.json                     |
|                                                                          |                        |
|  STEP 2: LIVE 3-STAGE SKILL <-> LLM AGENT TESTBENCH                      v                        |
|  (1) LLM (Local Ollama or Gemini/OpenAI/Claude) reads SKILL.md & selects MCP tool + JSON args     |
|  (2) Skill executes live HTTP endpoint (e.g. GET/POST http://127.0.0.1:8110/api/...) or MCP call  |
|  (3) LLM synthesizes a grounded natural-language response from the live application JSON          |
+---------------------------------------------------------------------------------------------------+
```

---

## Quickstart (End-to-End Web App → Skill → LLM Test)

Requires **only Python 3.10+ standard library** (zero `pip install` dependencies required):

### 1. *(Recommended)* Start Local Ollama Onboard Model
```bash
ollama pull llama3.2:3b
ollama serve
```
*(Or skip Ollama and select **Google Gemini**, **OpenAI**, or **Anthropic Claude** in the studio UI with an API key or `.env` variable.)*

### 2. Launch SkillForge AI Studio (`Port 8108`) & Companion Sample Web App (`TaskPulse` on `Port 8110`)
```bash
# Terminal 1 — Start SkillForge AI Studio on http://127.0.0.1:8108
./run.sh

# Terminal 2 — Start the bundled TaskPulse sample web app on http://127.0.0.1:8110
./examples/taskpulse-webapp/run.sh
```

### 3. Convert & Test Live in Your Browser
1. Open **`http://127.0.0.1:8108`**.
2. In **Step 1**, click **`⚡ Load Sample App (TaskPulse :8110)`** (or browse any application folder on your PC) and click **`✨ Convert Application into LLM Skill`**.
3. In **Step 2**, pick your **Skill Execution LLM** (**Local Ollama** onboard model by default, or switch to **Google Gemini / OpenAI / Anthropic**) and click **`📋 List all tasks`**, **`➕ Create a new task`**, or **`💰 Calculate budget (40h @ $150/hr)`** to watch the LLM read `SKILL.md`, call the live `TaskPulse` web app, and return a grounded answer.

---

## Command-Line Interface & MCP Hub (`cli.py` & `mcp_server.py`)

```bash
# List all 6 built-in security, governance & cloud engineering presets
python3 cli.py --list-presets

# Compile a preset and export all artifacts + deterministic .zip bundle to ./dist
python3 cli.py --compile aws-iam-least-privilege-auditor --out-dir ./dist

# Run 5-Gate verification & 3-run SHA-256 determinism check across all 6 presets
python3 cli.py --verify all

# Run MCP JSON-RPC 2.0 self-test (initialize, tools/list, resources/list, tools/call)
python3 mcp_server.py --self-test
```

### Connect to Claude Desktop / Cursor / Windsurf (`mcpServers`)
```json
{
  "mcpServers": {
    "skillforge-multi-skill-hub": {
      "command": "python3",
      "args": ["/path/to/skillforge-ai/mcp_server.py"],
      "env": {
        "SKILLFORGE_WORKSPACE": "/path/to/skillforge-ai/skills_workspace"
      }
    }
  }
}
```

---

## 6 Built-In Industry Presets

| Preset ID | Domain | Standards / Frameworks |
| :--- | :--- | :--- |
| `aws-iam-least-privilege-auditor` | Cloud Security (AWS IAM) | CIS AWS v3.0, NIST 800-53 AC-6, ISO 27001 A.8.2 |
| `k8s-zero-trust-network-verifier` | DevSecOps (Kubernetes) | NSA/CISA K8s v1.2, CIS Kubernetes v1.8, NIST 800-190 |
| `soc2-continuous-control-monitor` | GRC & Compliance | AICPA SOC 2 Type II (CC6/CC7/CC8), ISO 27001:2022 |
| `gdpr-pii-dataflow-lineage-scanner` | Data Privacy | GDPR Art. 25/30/32/44, CCPA/CPRA, HIPAA Safe Harbor |
| `openapi-idor-authz-triage-engine` | Application Security | OWASP API Top 10 (API1:2023), CWE-639, NIST AC-3 |
| `finops-cloud-cost-anomaly-detector` | Cloud FinOps | FinOps Foundation Framework, AWS Well-Architected |

---

## Running the Test Suite

```bash
python3 -m unittest discover -s tests -v
```

---

## License

Released under the [MIT License](LICENSE).
