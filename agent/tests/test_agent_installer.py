import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_installer import build_config


def args(**overrides):
    values = {
        "silent": True,
        "api_url": None,
        "username": None,
        "password": None,
        "organization": None,
        "default_username": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_silent_install_preserves_existing_config_when_args_are_omitted():
    existing = {
        "PRINTBILLING_API_URL": "https://billing.example.com/",
        "PRINTBILLING_AGENT_USER": "agent",
        "PRINTBILLING_AGENT_PASSWORD": "secret",
        "PRINTBILLING_ORGANIZATION_SLUG": "cliente-a",
        "PRINTBILLING_DEFAULT_USERNAME": "usuario-padrao",
    }

    config = build_config(existing, {}, args())

    assert config["PRINTBILLING_API_URL"] == "https://billing.example.com"
    assert config["PRINTBILLING_AGENT_USER"] == "agent"
    assert config["PRINTBILLING_AGENT_PASSWORD"] == "secret"
    assert config["PRINTBILLING_ORGANIZATION_SLUG"] == "cliente-a"
    assert config["PRINTBILLING_DEFAULT_USERNAME"] == "usuario-padrao"


def test_silent_install_can_clear_existing_default_username():
    existing = {
        "PRINTBILLING_API_URL": "https://billing.example.com",
        "PRINTBILLING_AGENT_USER": "agent",
        "PRINTBILLING_AGENT_PASSWORD": "secret",
        "PRINTBILLING_ORGANIZATION_SLUG": "cliente-a",
        "PRINTBILLING_DEFAULT_USERNAME": "usuario-antigo",
    }

    config = build_config(existing, {}, args(default_username=""))

    assert config["PRINTBILLING_DEFAULT_USERNAME"] == ""


def test_silent_reinstall_preserves_capture_and_update_flags():
    existing = {
        "PRINTBILLING_API_URL": "https://billing.example.com",
        "PRINTBILLING_AGENT_USER": "agent",
        "PRINTBILLING_AGENT_PASSWORD": "secret",
        "PRINTBILLING_CANCEL_BLOCKED": False,
        "PRINTBILLING_USE_PRINT_EVENT_LOG": False,
        "PRINTBILLING_AUTO_UPDATE": False,
        "PRINTBILLING_HEARTBEAT_INTERVAL": 120,
    }

    config = build_config(existing, {}, args(api_url="https://nova-api.example.com"))

    assert config["PRINTBILLING_API_URL"] == "https://nova-api.example.com"
    assert config["PRINTBILLING_CANCEL_BLOCKED"] is False
    assert config["PRINTBILLING_USE_PRINT_EVENT_LOG"] is False
    assert config["PRINTBILLING_AUTO_UPDATE"] is False
    assert config["PRINTBILLING_HEARTBEAT_INTERVAL"] == 120
