from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.security.secret_firewall import redact, scan

router = APIRouter(prefix="/copilot", tags=["copilot"])


class ScanRequest(BaseModel):
    text: str


@router.post("/scan")
def scan_secrets(req: ScanRequest):
    """Agent-gate secret check: an MCP/agent calls this before it's allowed to commit."""
    findings = scan(req.text)
    return {
        "clean": not findings,
        "findings": [{"kind": f.kind, "line": f.line_no} for f in findings],
        "redacted_preview": redact(req.text) if findings else None,
    }


@router.get("/capabilities")
def capabilities():
    return {
        "commit": "semantic staging + conventional message (planned)",
        "absorb": "amend edits into the right earlier commit, auto-restack (planned)",
        "checkpoint": "safe restorable save-points (planned)",
        "scan": "secret firewall (active)",
    }
