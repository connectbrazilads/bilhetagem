import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as agent_config


CONFIG_KEYS = [
    "PRINTBILLING_API_URL",
    "PRINTBILLING_AGENT_USER",
    "PRINTBILLING_AGENT_PASSWORD",
    "PRINTBILLING_ORGANIZATION_SLUG",
    "PRINTBILLING_CANCEL_BLOCKED",
    "PRINTBILLING_POLL_INTERVAL",
    "PRINTBILLING_DEFAULT_USERNAME",
    "PRINTBILLING_SNMP_POLL_INTERVAL",
    "PRINTBILLING_SNMP_COMMUNITY",
    "PRINTBILLING_SNMP_TIMEOUT_SECONDS",
    "PRINTBILLING_SNMP_RETRIES",
    "PRINTBILLING_USE_PRINT_EVENT_LOG",
    "PRINTBILLING_AUTO_UPDATE",
    "PRINTBILLING_UPDATE_CHECK_INTERVAL",
    "PRINTBILLING_HEARTBEAT_INTERVAL",
    "PRINTBILLING_QUEUE_ACTION_INTERVAL",
    "PRINTBILLING_SPOOL_SERVER",
    "PRINTBILLING_LOG_LEVEL",
]


def clear_env(monkeypatch):
    for key in CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_agent_config_falls_back_when_file_values_are_invalid(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setattr(
        agent_config,
        "file_config",
        {
            "PRINTBILLING_API_URL": " https://billing.example.com/ ",
            "PRINTBILLING_ORGANIZATION_SLUG": " ",
            "PRINTBILLING_POLL_INTERVAL": "zero",
            "PRINTBILLING_SNMP_POLL_INTERVAL": "-1",
            "PRINTBILLING_SNMP_TIMEOUT_SECONDS": "0",
            "PRINTBILLING_SNMP_RETRIES": "-2",
            "PRINTBILLING_USE_PRINT_EVENT_LOG": "talvez",
            "PRINTBILLING_CANCEL_BLOCKED": "nao",
            "PRINTBILLING_AUTO_UPDATE": "sim",
            "PRINTBILLING_UPDATE_CHECK_INTERVAL": "30",
            "PRINTBILLING_HEARTBEAT_INTERVAL": "5",
            "PRINTBILLING_QUEUE_ACTION_INTERVAL": "1",
            "PRINTBILLING_DEFAULT_USERNAME": " DIEGO_LCD ",
            "PRINTBILLING_SPOOL_SERVER": " ",
            "PRINTBILLING_LOG_LEVEL": "verbose",
        },
    )

    config = agent_config.AgentConfig()

    assert config.api_base_url == "https://billing.example.com"
    assert config.organization_slug is None
    assert config.poll_interval_seconds == 5
    assert config.snmp_poll_interval_seconds == 60
    assert config.snmp_timeout_seconds == 2.0
    assert config.snmp_retries == 1
    assert config.use_print_event_log is True
    assert config.cancel_blocked_jobs is False
    assert config.auto_update_enabled is True
    assert config.update_check_interval_seconds == 3600
    assert config.heartbeat_interval_seconds == 60
    assert config.queue_action_interval_seconds == 30
    assert config.default_username == "DIEGO_LCD"
    assert config.spool_server is None
    assert config.log_level == "INFO"


def test_agent_config_environment_overrides_file_config(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setattr(
        agent_config,
        "file_config",
        {
            "PRINTBILLING_API_URL": "https://file.example.com",
            "PRINTBILLING_POLL_INTERVAL": 5,
            "PRINTBILLING_USE_PRINT_EVENT_LOG": True,
        },
    )
    monkeypatch.setenv("PRINTBILLING_API_URL", " https://env.example.com/ ")
    monkeypatch.setenv("PRINTBILLING_POLL_INTERVAL", "9")
    monkeypatch.setenv("PRINTBILLING_USE_PRINT_EVENT_LOG", "false")
    monkeypatch.setenv("PRINTBILLING_LOG_LEVEL", "debug")

    config = agent_config.AgentConfig()

    assert config.api_base_url == "https://env.example.com"
    assert config.poll_interval_seconds == 9
    assert config.use_print_event_log is False
    assert config.log_level == "DEBUG"


def test_agent_config_runtime_validation_accepts_secure_credentials():
    config = agent_config.AgentConfig(
        api_base_url="https://billing.example.com",
        api_username="agent",
        api_password="AgentPassword2026",
        organization_slug="cliente-a",
    )

    config.validate_for_runtime()


def test_agent_config_runtime_validation_rejects_unsafe_password():
    config = agent_config.AgentConfig(
        api_base_url="https://billing.example.com",
        api_username="agent",
        api_password="agent12345",
        organization_slug="cliente-a",
    )

    try:
        config.validate_for_runtime()
    except RuntimeError as exc:
        assert "senha exclusiva" in str(exc).lower()
    else:
        raise AssertionError("Agent nao deve iniciar com senha padrao/insegura")


def test_agent_config_runtime_validation_rejects_missing_organization_slug():
    config = agent_config.AgentConfig(
        api_base_url="https://billing.example.com",
        api_username="agent",
        api_password="AgentPassword2026",
        organization_slug=None,
    )

    try:
        config.validate_for_runtime()
    except RuntimeError as exc:
        assert "slug da empresa" in str(exc).lower()
    else:
        raise AssertionError("Agent nao deve iniciar sem slug da empresa")
