#!/usr/bin/env python3
"""BillingOps Diagnostics Reference Web App (Port 8115) — Sample Target App for SkillForge AI.

Exposes read-only Linux log anomaly triage, read-only Oracle V$SESSION lock inspection,
microservice correlation-ID tracing, and gated Jira RCA draft generation so users can
compile an operational diagnostics web app into a verified SKILL.md + MCP server in 1 click.
"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import urlparse


class BillingOpsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_json(self, payload: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json({"status": "ok", "service": "billing-ops-diagnostics-webapp", "read_only_mode": True})
            return
        if path == "/api/logs/anomalies":
            self._send_json({
                "host": "billing-worker-04",
                "scanned_lines": 48200,
                "error_count": 19,
                "oracle_codes": {"ORA-00060": 4},
                "top_correlation_id": "corr-99418a",
            })
            return
        if path == "/api/oracle/locks":
            self._send_json({
                "read_only_verified": True,
                "blocking_sessions": [
                    {"waiting_sid": 418, "blocking_sid": 109, "table": "INVOICE_LEDGER", "seconds_in_wait": 342}
                ],
            })
            return
        if path == "/api/microservices/trace":
            self._send_json({
                "correlation_id": "corr-99418a",
                "hops": [
                    {"service": "api-gateway", "status": 504, "latency_ms": 9002},
                    {"service": "billing-api", "status": 504, "latency_ms": 8940},
                    {"service": "ledger-service", "status": 500, "error": "ORA-00060 row lock timeout"},
                ],
            })
            return
        self._send_json({"error": f"Unknown route: {path}"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
        if path == "/api/incidents/draft-rca":
            self._send_json({
                "ticket_draft": {
                    "project": "BILLOPS",
                    "summary": body.get("summary", "Nightly Invoice Batch Stall — ORA-00060 Lock on INVOICE_LEDGER"),
                    "hitl_approval_required": True,
                    "remediation_status": "PENDING_OPERATOR_APPROVAL",
                }
            })
            return
        self._send_json({"error": f"Unknown POST route: {path}"}, status=HTTPStatus.NOT_FOUND)


def run_billing_ops_server(host: str = "127.0.0.1", port: int = 8115) -> None:
    httpd = ThreadingHTTPServer((host, port), BillingOpsHandler)
    print(f"BillingOps Sample Web App listening on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8115)
    ns = ap.parse_args()
    run_billing_ops_server(ns.host, ns.port)
