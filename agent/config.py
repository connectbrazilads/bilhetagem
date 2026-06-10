from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
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


def _raw_config_value(key: str, default):
    env_value = os.getenv(key)
    if env_value is not None:
        return env_value
    return file_config.get(key, default)


def _config_str(key: str, default: str = "", *, strip_trailing_slash: bool = False) -> str:
    value = str(_raw_config_value(key, default)).strip()
    if strip_trailing_slash:
        value = value.rstrip("/")
    return value


def _config_optional_str(key: str, default: str | None = None) -> str | None:
    value = _raw_config_value(key, default)
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _config_bool(key: str, default: bool) -> bool:
    value = _raw_config_value(key, default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "sim"):
        return True
    if normalized in ("false", "0", "no", "nao", "não"):
        return False
    return default


def _config_int(key: str, default: int, *, min_value: int | None = None) -> int:
    value = _raw_config_value(key, default)
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


def _config_float(key: str, default: float, *, min_value: float | None = None) -> float:
    value = _raw_config_value(key, default)
    try:
        parsed = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


@dataclass(frozen=True)
class AgentConfig:
    api_base_url: str = field(default_factory=lambda: _config_str("PRINTBILLING_API_URL", "http://localhost:8000", strip_trailing_slash=True))
    api_username: str = field(default_factory=lambda: _config_str("PRINTBILLING_AGENT_USER", "agent"))
    api_password: str = field(default_factory=lambda: _config_str("PRINTBILLING_AGENT_PASSWORD", "change-me-agent-password"))
    organization_slug: str | None = field(default_factory=lambda: _config_optional_str("PRINTBILLING_ORGANIZATION_SLUG", "default"))
    poll_interval_seconds: int = field(default_factory=lambda: _config_int("PRINTBILLING_POLL_INTERVAL", 5, min_value=1))
    snmp_poll_interval_seconds: int = field(default_factory=lambda: _config_int("PRINTBILLING_SNMP_POLL_INTERVAL", 60, min_value=1))
    snmp_community: str = field(default_factory=lambda: _config_str("PRINTBILLING_SNMP_COMMUNITY", "public"))
    snmp_timeout_seconds: float = field(default_factory=lambda: _config_float("PRINTBILLING_SNMP_TIMEOUT_SECONDS", 2.0, min_value=0.1))
    snmp_retries: int = field(default_factory=lambda: _config_int("PRINTBILLING_SNMP_RETRIES", 1, min_value=0))
    default_username: str | None = field(default_factory=lambda: _config_optional_str("PRINTBILLING_DEFAULT_USERNAME"))
    use_print_event_log: bool = field(default_factory=lambda: _config_bool("PRINTBILLING_USE_PRINT_EVENT_LOG", True))
    cancel_blocked_jobs: bool = field(default_factory=lambda: _config_bool("PRINTBILLING_CANCEL_BLOCKED", True))
    auto_update_enabled: bool = field(default_factory=lambda: _config_bool("PRINTBILLING_AUTO_UPDATE", True))
    update_check_interval_seconds: int = field(default_factory=lambda: _config_int("PRINTBILLING_UPDATE_CHECK_INTERVAL", 3600, min_value=60))
    heartbeat_interval_seconds: int = field(default_factory=lambda: _config_int("PRINTBILLING_HEARTBEAT_INTERVAL", 60, min_value=10))
    queue_action_interval_seconds: int = field(default_factory=lambda: _config_int("PRINTBILLING_QUEUE_ACTION_INTERVAL", 30, min_value=5))
    spool_server: str | None = field(default_factory=lambda: _config_optional_str("PRINTBILLING_SPOOL_SERVER"))


config = AgentConfig()
