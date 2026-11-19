#!/usr/bin/env python3
"""TaskPulse — Lightweight Operations & Budget Web Application (Port 8110) designed
to be converted into an LLM Agent Skill and tested live with SkillForge AI.

Exposes 4 clean REST API endpoints:
  - GET  /api/health            -> Returns live server status and task counts
  - GET  /api/tasks             -> Lists all tasks in the application
  - POST /api/tasks             -> Creates a new task {"title": "...", "priority": "HIGH", "owner": "..."}
  - POST /api/calculate-budget  -> Deterministic budget calculator {"hours": 40, "hourly_rate": 150, "tax_pct": 8.25}
"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent

TASKS_DB: List[Dict[str, Any]] = [
    {"id": "TSK-101", "title": "Configure Local Ollama LLM Bridge", "priority": "HIGH", "status": "COMPLETED", "owner": "AI Ops"},
    {"id": "TSK-102", "title": "Convert TaskPulse Web App into an LLM Skill", "priority": "HIGH", "status": "IN_PROGRESS", "owner": "SkillForge"},
    {"id": "TSK-103", "title": "Verify MCP Tool Execution from LLM Chat", "priority": "MEDIUM", "status": "OPEN", "owner": "QA Team"},
]


def get_application_health() -> Dict[str, Any]:
    """Return live health status and task counts for the TaskPulse Test Web App."""
    return {
        "status": "ok",
        "app_name": "TaskPulse Test Web App",
        "port": 8110,
        "total_tasks": len(TASKS_DB),
        "open_tasks": sum(1 for t in TASKS_DB if t["status"] != "COMPLETED"),
    }


def list_all_tasks() -> Dict[str, Any]:
    """Return the complete list of tasks stored in the TaskPulse Test Web App."""
    return {
        "tasks": TASKS_DB,
        "count": len(TASKS_DB),
    }


def create_new_task(title: str, priority: str = "HIGH", owner: str = "LLM Skill Agent") -> Dict[str, Any]:
    """Create a new task in the TaskPulse Test Web App and return the created record."""
    new_id = f"TSK-{101 + len(TASKS_DB)}"
    task = {
        "id": new_id,
        "title": title.strip() or f"Automated Task {new_id}",
        "priority": priority.upper() if priority else "HIGH",
        "status": "OPEN",
        "owner": owner or "LLM Skill Agent",
    }
    TASKS_DB.append(task)
    return {"created": task, "total_tasks": len(TASKS_DB)}


def calculate_project_budget(hours: float = 40.0, hourly_rate: float = 150.0, tax_pct: float = 8.25) -> Dict[str, Any]:
    """Deterministically calculate project subtotal, tax amount, and grand total cost."""
    subtotal = round(float(hours) * float(hourly_rate), 2)
    tax_amount = round(subtotal * (float(tax_pct) / 100.0), 2)
    grand_total = round(subtotal + tax_amount, 2)
    return {
        "hours": float(hours),
        "hourly_rate_usd": float(hourly_rate),
        "subtotal_usd": subtotal,
        "tax_pct": float(tax_pct),
        "tax_amount_usd": tax_amount,
        "grand_total_usd": grand_total,
    }


class TaskPulseHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(get_application_health())
            return
        if path == "/api/tasks":
            self._send_json(list_all_tasks())
            return
        if path in ("/", "/index.html"):
            html_bytes = (ROOT_DIR / "index.html").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)
            return
        self._send_json({"error": f"Not found: {path}"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = self._read_json()
        if path == "/api/tasks":
            title = str(body.get("title") or body.get("task") or "New Task from LLM Skill")
            priority = str(body.get("priority") or "HIGH")
            owner = str(body.get("owner") or "LLM Skill Agent")
            self._send_json(create_new_task(title, priority, owner))
            return
        if path == "/api/calculate-budget":
            hours = float(body.get("hours", 40.0))
            rate = float(body.get("hourly_rate", 150.0))
            tax = float(body.get("tax_pct", 8.25))
            self._send_json(calculate_project_budget(hours, rate, tax))
            return
        self._send_json({"error": f"Unknown endpoint: {path}"}, status=HTTPStatus.NOT_FOUND)


def main() -> int:
    parser = argparse.ArgumentParser(description="TaskPulse Test Web App (Port 8110)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8110)
    args = parser.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), TaskPulseHandler)
    print(f"TaskPulse Test Web App listening on http://{args.host}:{args.port}")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
