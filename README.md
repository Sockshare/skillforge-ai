# SkillForge AI — Web-App-to-Agent-Skill (`SKILL.md`), Deterministic CLI & MCP Compiler Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-indigo.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B%20Zero--Dependency-10b981.svg)](server.py)
[![MCP JSON-RPC 2.0](https://img.shields.io/badge/MCP-JSON--RPC%202.0%20%282024--11--05%29-06b6d4.svg)](mcp_server.py)
[![Determinism Verified](https://img.shields.io/badge/Determinism-3--Run%20SHA--256%20Verified-f59e0b.svg)](cli.py)

**SkillForge AI** is a zero-dependency, full-stack open-source compiler studio that transforms any web application workflow, **OpenAPI 3.1** specification, Python/TypeScript module, or security/compliance blueprint into a cryptographically verified **AI Agent Skill Package**:

1. **`SKILL.md`** — Open-standard Agent Skill specification with validated YAML frontmatter (`name`, `description`, `version`), operational guardrails, control matrices, and step-by-step agent instructions (compatible with Claude Code, Cursor, Windsurf, Codex CLI, and open-source agent runtimes).
2. **`mcp_server.py`** — Standalone **Model Context Protocol (MCP JSON-RPC 2.0)** server implementing `initialize`, `tools/list`, and `tools/call` over stdio and HTTP.
3. **`scripts/engine.py`** — Zero-dependency deterministic Python 3 CLI evaluation engine with canonical JSON key sorting and `SHA-256` output hashing.
4. **`references/schema.json`** — Strict **JSON Schema Draft 2020-12** input/output contracts plus ready-to-use adapters for **OpenAI Function Calling** and **LangGraph `StructuredTool`**.
5. **`tests/test_skill.py`** — Automated unit and 3-run `SHA-256` determinism verification test suite.

---

## Architecture Overview

```
+---------------------------------------------------------------------------------------------------+
|                                   SKILLFORGE AI COMPILER STUDIO                                   |
|                                                                                                   |
|  +-----------------------+    +------------------------+    +----------------------------------+  |
|  | Stage 1: Architect    | -> | Stage 2: Synthesizer   | -> | Stage 3: 5-Gate Verifier         |  |
|  | - OpenAPI 3.1 / JSON  |    | - SKILL.md Frontmatter |    | - Gate 1: SKILL.md YAML Schema   |  |
|  | - JSON Schema 2020-12 |    | - scripts/engine.py    |    | - Gate 2: Python AST Security    |  |
|  | - Guardrail Extractor |    | - mcp_server.py        |    | - Gate 3: Tool Schema Contract   |  |
|  +-----------------------+    +------------------------+    | - Gate 4: 3-Run SHA-256 Match    |  |
|                                                             | - Gate 5: MCP JSON-RPC Handshake |  |
|                                                             +-----------------+----------------+  |
|                                                                               |                   |
|                                                                               v                   |
|                                                             +----------------------------------+  |
|                                                             | Stage 4: Multi-Artifact Packager |  |
|                                                             | - Deterministic .zip Bundle      |  |
|                                                             +----------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

---

## 6 Built-In Industry Presets (1-Click Load in UI & CLI)

| Preset ID | Domain | Standards / Frameworks | What It Verifies |
| :--- | :--- | :--- | :--- |
| `aws-iam-least-privilege-auditor` | Cloud Security (AWS IAM) | CIS AWS v3.0, NIST 800-53 AC-6, ISO 27001 A.8.2 | Audits AWS IAM identity & trust policies for wildcard `*` actions, `iam:PassRole` privilege escalation, missing `sts:ExternalId`/MFA conditions, and stale access keys (>90 days). |
| `k8s-zero-trust-network-verifier` | DevSecOps (Kubernetes) | NSA/CISA K8s v1.2, CIS Kubernetes v1.8, NIST 800-190 | Verifies default-deny Ingress/Egress `NetworkPolicies`, privileged containers, `cluster-admin` bindings, and read-only root filesystems. |
| `soc2-continuous-control-monitor` | GRC & Compliance | AICPA SOC 2 Type II (CC6/CC7/CC8), ISO 27001:2022 | Evaluates phishing-resistant MFA enforcement, AWS KMS key rotation, 365-day SIEM audit log retention, and GitHub branch protection rules. |
| `gdpr-pii-dataflow-lineage-scanner` | Data Privacy | GDPR Art. 25/30/32/44, CCPA/CPRA, HIPAA Safe Harbor | Scans PostgreSQL/Snowflake DDL schemas and ETL sinks for unencrypted PII/PHI columns, missing retention TTLs, and unapproved cross-border transfers. |
| `openapi-idor-authz-triage-engine` | Application Security | OWASP API Top 10 (API1:2023), CWE-639, NIST AC-3 | Multi-gate source-to-sink authorization verifier checking OpenAPI 3.1 routes, OAuth2 scopes, and SQL tenant ownership guards to separate True Positive BOLA/IDORs from False Positives. |
| `finops-cloud-cost-anomaly-detector` | Cloud FinOps | FinOps Foundation Framework, AWS Well-Architected | Analyzes Terraform & Kubernetes telemetry for idle GPU nodes (<15% utilization), orphaned EBS volumes (>14 days), and missing cost allocation tags. |

---

## Quickstart

### 1. Launch the Interactive Web Studio (`http://127.0.0.1:8091`)

Requires **only Python 3.10+ standard library** (zero `pip install` dependencies required):

```bash
./run.sh
# Or directly:
python3 server.py --host 127.0.0.1 --port 8091
```

 You can also open `index.html` directly in any browser or host the repository on **GitHub Pages** — the frontend includes an in-browser deterministic compiler and Web Crypto `SHA-256` engine.

### 2. Command-Line Interface (`cli.py`)

```bash
# List all 6 built-in industry presets
python3 cli.py --list-presets

# Compile a preset and export all artifacts + deterministic .zip bundle to ./dist
python3 cli.py --compile aws-iam-least-privilege-auditor --out-dir ./dist

# Run 5-Gate verification & 3-run SHA-256 determinism check across all 6 presets
python3 cli.py --verify all
```

### 3. Model Context Protocol (`mcp_server.py`)

```bash
# Run self-test verifying initialize, tools/list, and tools/call
python3 mcp_server.py --self-test

# Connect via Claude Desktop / Cursor / Windsurf MCP configuration:
```

```json
{
  "mcpServers": {
    "skillforge-ai": {
      "command": "python3",
      "args": ["/path/to/skillforge-ai/mcp_server.py"]
    }
  }
}
```

---

## 5-Gate Quality, Security & Determinism Verification

Every skill compiled by SkillForge AI must pass 5 automated verification gates before packaging:

1. **Gate 1 — YAML Frontmatter & `SKILL.md` Schema Compliance**: Verifies valid YAML frontmatter (`name`, `description`, `version`), guardrails, and CLI/MCP invocation sections.
2. **Gate 2 — Static Security & Injection AST Verifier**: Parses generated Python scripts (`scripts/engine.py`, `mcp_server.py`, `tests/test_skill.py`) with Python's `ast` module and enforces zero `eval()`, `exec()`, or shell injection primitives.
3. **Gate 3 — JSON Schema Draft 2020-12 Contract Check**: Validates strict input/output JSON Schemas and multi-framework adapters (MCP, OpenAI Function Calling, LangGraph).
4. **Gate 4 — 3-Run Cryptographic Determinism Check (`SHA-256`)**: Executes the compiled skill 3 consecutive times on sample workloads and asserts `Run 1 SHA-256 == Run 2 SHA-256 == Run 3 SHA-256`.
5. **Gate 5 — MCP `JSON-RPC 2.0` Handshake Verification**: Exercises `initialize`, `tools/list`, and `tools/call` against the generated MCP server.

---

## Running the Test Suite

```bash
python3 -m unittest discover -s tests -v
```

---

## License

Released under the [MIT License](LICENSE).
