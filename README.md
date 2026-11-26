# SkillForge AI — 1:1 `skill-creator` Workbench, Standalone Headless CLI Synthesizer, Multi-Skill Orchestrator & Local Ollama Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-indigo.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B%20Zero--Dependency-10b981.svg)](server.py)
[![Primary Engine: Local Ollama](https://img.shields.io/badge/Default%20LLM-Any%20Installed%20Local%20Ollama%20Model-22c55e.svg)](#live-local-ollama-integration--optional-cloud-apis)
[![MCP JSON-RPC 2.0](https://img.shields.io/badge/MCP-JSON--RPC%202.0%20%282024--11--05%29-06b6d4.svg)](mcp_server.py)
[![Determinism Verified](https://img.shields.io/badge/Determinism-Two--Run%20%26%203--Run%20SHA--256%20Verified-f59e0b.svg)](cli.py)

**SkillForge AI** is a zero-dependency, local-first skill engineering studio (`http://127.0.0.1:8108`) with **0% functional gap** between:
1. **The Official `skill-creator` (Skill Builder) Meta-Skill:**
   - Guided **Intent Interview** (powered by any installed **Local Ollama** model or optional Cloud API)
   - **Python AST Web-App Decoupler & Standalone Headless CLI Synthesizer** (`SKILL.md`, `scripts/<slug>_cli.py`, `resources/reporting_engine.py`, `BUILD.bazel`, `INSTALL.md`, `README.md`, `evals/evals.json`, `mcp_server.py` — **runs 100% standalone from CLI with zero web server required**)
   - **Real Subprocess Paired Evaluations (`with_skill` vs. `without_skill` / `old_skill`)** writing real outputs on disk inside `eval_workspaces/<slug>-workspace/iteration-<N>/` (`eval_metadata.json`, `timing.json`, `grading.json`, `benchmark.json`, `benchmark.md`, blind comparator, and standalone static `eval_viewer.html`)
   - **Human Review (`feedback.json`) & Iterative `SKILL.md` Rewriter** (`skill-snapshot/` + Ollama generalized refinement -> `iteration-<N+1>`)
   - **60/40 Train/Held-Out Test YAML Trigger Description Optimizer** updating `SKILL.md` frontmatter directly + `.skill.zip` packager
2. **Multi-Skill Sequential Orchestration Layer, Master Executive Reporter & Two-Run `SHA-256` Determinism Studio:**
   - **Stage 1 Upstream Discovery** strictly filters out `dev/test/staging/qa/sandbox` non-prod noise and emits `00_Verified_Scope_and_Groups/discovered_items.txt` + verification CSV
   - **Stages 2..N Verification & Vulnerability SLA Scanners** consume `--handoff-in` sequentially
   - **Master Executive Synthesis Reporter** generates `Canonical_Reviewed_Dataset.json` (`dataset_sha256` + per-stage sub-hashes), `<App>_Finalized_Master_Report.md` (`report_sha256` + **5-Layer Architecture Mermaid Diagram**), `Finalized_Master_Executive_Summary.html`, and `Cryptographic_Verification_Manifest.json`
   - **Two-Run Independent Determinism Verifier** executes `Run_A/` and `Run_B/` in clean directories and proves byte-for-byte `Run A SHA-256 == Run B SHA-256`
   - **Unified 1-Command Launcher CLI (`./<pipeline>-cli`)** supporting `list`, `stage`, `all`, `report`, `compare`, and `verify`
3. **Enterprise Runtime Guardrails (`PreToolUse`/`PostToolUse`), 100-Skill Progressive-Disclosure Router & 14-File Starter Kit.**

---

## Live Local Ollama Integration + Optional Cloud APIs

SkillForge AI dynamically queries your local Ollama daemon (`GET http://127.0.0.1:11434/api/tags` or any custom `OLLAMA_HOST` URL) via `/api/ollama/models`, filters out embedding-only models, and populates the **Global Ollama Model Selector** with **every chat/coder model you have installed** (e.g., `qwen2.5-coder:7b`, `llama3.2:3b`, `deepseek-coder`, `mistral`, etc.):

```bash
# Install any model you want in Ollama — SkillForge AI auto-discovers it live!
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
ollama serve
```

Optional Cloud APIs (**Google Gemini**, **OpenAI / OpenRouter**, **Anthropic Claude**) are also supported via session API keys or `.env` variables, and deterministic Python fallbacks guarantee offline/CI operation even when no LLM daemon is running.

---

## Quickstart

Requires **only Python 3.10+ standard library** (zero `pip install` packages needed):

```bash
# Start SkillForge AI Studio on http://127.0.0.1:8108
./run.sh

# Optional companion sample web apps for live HTTP bridge testing:
./examples/taskpulse-webapp/run.sh      # Port 8110
python3 examples/billing-ops-webapp/server.py --port 8115
```

---

## Key REST API & MCP Capabilities

| Capability | HTTP Endpoint | MCP Tool (`mcp_server.py`) |
| :--- | :--- | :--- |
| **Live Installed Ollama Models** | `GET /api/ollama/models?url=...` | `list_llm_profiles` |
| **1:1 `skill-creator` Intent Interview** | `POST /api/skill-creator/interview` | — |
| **Decouple Web App -> Standalone Headless CLI Skill** | `POST /api/skill-creator/build-standalone` | `build_standalone_headless_skill` |
| **Real Subprocess `with_skill` vs `without_skill` Evals** | `POST /api/skill-creator/run-evals` | `run_real_skill_creator_evals` |
| **`feedback.json` + Ollama Rewrite -> `iteration-<N+1>`** | `POST /api/skill-creator/submit-feedback` | — |
| **60/40 Trigger Optimizer -> `SKILL.md` Frontmatter** | `POST /api/skill-creator/optimize-description` | `run_skill_creator_benchmark` |
| **Package Distributable `.skill.zip`** | `POST /api/skill-creator/package.skill` | — |
| **Provision 6-Skill Reference Compliance Pipeline** | `POST /api/orchestrator/provision-reference-suite` | — |
| **Compile Custom Multi-Skill Sequential Orchestrator** | `POST /api/orchestrator/compile` | `compile_skill_orchestrator` |
| **Run Pipeline (`single_stage` / `full_workflow` / `two_run_determinism`)** | `POST /api/orchestrator/run` | `run_orchestrated_pipeline` |
| **Download Complete Orchestrator + Stage Skills `.zip`** | `POST /api/orchestrator/bundle.zip` | — |
| **Runtime `PreToolUse` Guardrail Hook Evaluator** | `POST /api/kit/guardrails/test` | `evaluate_pretooluse_guardrail` |
| **100-Skill Progressive-Disclosure BM25 Router** | `POST /api/kit/router` | `route_hundred_skills_progressive` |
| **14-File Agent Engineering Starter Kit `.zip`** | `POST /api/kit/starter-bundle.zip` | `generate_agent_engineering_kit` |

---

## Verification & Test Suite

```bash
python3 -m unittest discover -s tests -v
node --check static/js/app.js
python3 mcp_server.py --self-test
python3 cli.py --verify all
```

---

## License

Released under the [MIT License](LICENSE).
