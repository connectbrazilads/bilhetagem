from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


def get_app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def load_file_config() -> dict:
    config_path = get_app_dir() / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Erro ao ler config.json: {e}", file=sys.stderr)
    return {}


file_config = load_file_config()


@dataclass(frozen=True)
class AgentConfig:
    api_base_url: str = os.getenv(
        "PRINTBILLING_API_URL",
        file_config.get("PRINTBILLING_API_URL", "http://localhost:8000")
    )
    api_username: str = os.getenv(
        "PRINTBILLING_AGENT_USER",
        file_config.get("PRINTBILLING_AGENT_USER", "agent")
    )
    api_password: str = os.getenv(
        "PRINTBILLING_AGENT_PASSWORD",
        file_config.get("PRINTBILLING_AGENT_PASSWORD", "change-me-agent-password")
    )
    poll_interval_seconds: int = int(
        os.getenv(
            "PRINTBILLING_POLL_INTERVAL",
            file_config.get("PRINTBILLING_POLL_INTERVAL", "5")
        )
    )
    cancel_blocked_jobs: bool = str(
        os.getenv(
            "PRINTBILLING_CANCEL_BLOCKED",
            file_config.get("PRINTBILLING_CANCEL_BLOCKED", True)
        )
    ).lower() == "true"
    spool_server: str | None = os.getenv(
        "PRINTBILLING_SPOOL_SERVER",
        file_config.get("PRINTBILLING_SPOOL_SERVER")
    ) or None


config = AgentConfig()
