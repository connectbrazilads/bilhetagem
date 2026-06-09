from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    api_base_url: str = os.getenv("PRINTBILLING_API_URL", "http://localhost:8000")
    api_username: str = os.getenv("PRINTBILLING_AGENT_USER", "agent")
    api_password: str = os.getenv("PRINTBILLING_AGENT_PASSWORD", "change-me-agent-password")
    poll_interval_seconds: int = int(os.getenv("PRINTBILLING_POLL_INTERVAL", "5"))
    cancel_blocked_jobs: bool = os.getenv("PRINTBILLING_CANCEL_BLOCKED", "true").lower() == "true"
    spool_server: str | None = os.getenv("PRINTBILLING_SPOOL_SERVER") or None


config = AgentConfig()
