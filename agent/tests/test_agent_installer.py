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


def test_silent_install_trims_text_values_before_writing_config():
    config = build_config(
        {},
        {},
        args(
            api_url=" https://billing.example.com/ ",
            username=" agent ",
            password=" secret ",
            organization=" cliente-a ",
            default_username=" DIEGO LCD ",
        ),
    )

    assert config["PRINTBILLING_API_URL"] == "https://billing.example.com"
    assert config["PRINTBILLING_AGENT_USER"] == "agent"
    assert config["PRINTBILLING_AGENT_PASSWORD"] == "secret"
    assert config["PRINTBILLING_ORGANIZATION_SLUG"] == "cliente-a"
    assert config["PRINTBILLING_DEFAULT_USERNAME"] == "DIEGO LCD"


def test_silent_reinstall_preserves_capture_and_update_flags():
    existing = {
        "PRINTBILLING_API_URL": "https://billing.example.com",
        "PRINTBILLING_AGENT_USER": "agent",
        "PRINTBILLING_AGENT_PASSWORD": "secret",
        "PRINTBILLING_ORGANIZATION_SLUG": "cliente-a",
        "PRINTBILLING_CANCEL_BLOCKED": False,
        "PRINTBILLING_USE_PRINT_EVENT_LOG": False,
        "PRINTBILLING_AUTO_UPDATE": False,
        "PRINTBILLING_HEARTBEAT_INTERVAL": 120,
    }

    config = build_config(existing, {}, args(api_url="https://nova-api.example.com"))

    assert config["PRINTBILLING_API_URL"] == "https://nova-api.example.com"
    assert config["PRINTBILLING_ORGANIZATION_SLUG"] == "cliente-a"
    assert config["PRINTBILLING_CANCEL_BLOCKED"] is False
    assert config["PRINTBILLING_USE_PRINT_EVENT_LOG"] is False
    assert config["PRINTBILLING_AUTO_UPDATE"] is False
    assert config["PRINTBILLING_HEARTBEAT_INTERVAL"] == 120


def test_silent_new_install_requires_explicit_organization_slug():
    try:
        build_config(
            {},
            {},
            args(
                api_url="https://billing.example.com",
                username="agent",
                password="secret",
            ),
        )
    except RuntimeError as exc:
        assert "--organization" in str(exc)
    else:
        raise AssertionError("Instalacao silenciosa nova deveria exigir --organization")


def test_silent_new_install_ignores_template_credentials_for_required_fields():
    template = {
        "PRINTBILLING_API_URL": "https://template.example.com",
        "PRINTBILLING_AGENT_USER": "agent",
        "PRINTBILLING_AGENT_PASSWORD": "agent12345",
        "PRINTBILLING_ORGANIZATION_SLUG": "default",
    }

    try:
        build_config({}, template, args())
    except RuntimeError as exc:
        assert "--password" in str(exc)
        assert "--organization" in str(exc)
    else:
        raise AssertionError("Instalacao silenciosa nova nao deve usar credenciais do template")
