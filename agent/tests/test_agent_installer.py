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
        "spool_server": None,
        "log_level": None,
        "cancel_blocked": None,
        "use_print_event_log": None,
        "auto_update": None,
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
        "PRINTBILLING_SPOOL_SERVER": r"\\PRINTSERVER",
        "PRINTBILLING_LOG_LEVEL": "DEBUG",
    }

    config = build_config(existing, {}, args())

    assert config["PRINTBILLING_API_URL"] == "https://billing.example.com"
    assert config["PRINTBILLING_AGENT_USER"] == "agent"
    assert config["PRINTBILLING_AGENT_PASSWORD"] == "secret"
    assert config["PRINTBILLING_ORGANIZATION_SLUG"] == "cliente-a"
    assert config["PRINTBILLING_DEFAULT_USERNAME"] == "usuario-padrao"
    assert config["PRINTBILLING_SPOOL_SERVER"] == r"\\PRINTSERVER"
    assert config["PRINTBILLING_LOG_LEVEL"] == "DEBUG"


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
            spool_server=r" \\PRINTSERVER ",
        ),
    )

    assert config["PRINTBILLING_API_URL"] == "https://billing.example.com"
    assert config["PRINTBILLING_AGENT_USER"] == "agent"
    assert config["PRINTBILLING_AGENT_PASSWORD"] == "secret"
    assert config["PRINTBILLING_ORGANIZATION_SLUG"] == "cliente-a"
    assert config["PRINTBILLING_DEFAULT_USERNAME"] == "DIEGO LCD"
    assert config["PRINTBILLING_SPOOL_SERVER"] == r"\\PRINTSERVER"


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
        "PRINTBILLING_SPOOL_SERVER": r"\\PRINTSERVER",
    }

    config = build_config(existing, {}, args(api_url="https://nova-api.example.com"))

    assert config["PRINTBILLING_API_URL"] == "https://nova-api.example.com"
    assert config["PRINTBILLING_ORGANIZATION_SLUG"] == "cliente-a"
    assert config["PRINTBILLING_CANCEL_BLOCKED"] is False
    assert config["PRINTBILLING_USE_PRINT_EVENT_LOG"] is False
    assert config["PRINTBILLING_AUTO_UPDATE"] is False
    assert config["PRINTBILLING_HEARTBEAT_INTERVAL"] == 120
    assert config["PRINTBILLING_SPOOL_SERVER"] == r"\\PRINTSERVER"


def test_silent_reinstall_falls_back_when_existing_numeric_flags_are_invalid():
    existing = {
        "PRINTBILLING_API_URL": "https://billing.example.com",
        "PRINTBILLING_AGENT_USER": "agent",
        "PRINTBILLING_AGENT_PASSWORD": "secret",
        "PRINTBILLING_ORGANIZATION_SLUG": "cliente-a",
        "PRINTBILLING_CANCEL_BLOCKED": "talvez",
        "PRINTBILLING_USE_PRINT_EVENT_LOG": "nao",
        "PRINTBILLING_AUTO_UPDATE": "sim",
        "PRINTBILLING_POLL_INTERVAL": "zero",
        "PRINTBILLING_SNMP_POLL_INTERVAL": "-1",
        "PRINTBILLING_SNMP_TIMEOUT_SECONDS": "0",
        "PRINTBILLING_SNMP_RETRIES": "-2",
        "PRINTBILLING_UPDATE_CHECK_INTERVAL": "30",
        "PRINTBILLING_HEARTBEAT_INTERVAL": "5",
        "PRINTBILLING_QUEUE_ACTION_INTERVAL": "1",
    }

    config = build_config(existing, {}, args())

    assert config["PRINTBILLING_CANCEL_BLOCKED"] is True
    assert config["PRINTBILLING_USE_PRINT_EVENT_LOG"] is False
    assert config["PRINTBILLING_AUTO_UPDATE"] is True
    assert config["PRINTBILLING_POLL_INTERVAL"] == 5
    assert config["PRINTBILLING_SNMP_POLL_INTERVAL"] == 60
    assert config["PRINTBILLING_SNMP_TIMEOUT_SECONDS"] == 2.0
    assert config["PRINTBILLING_SNMP_RETRIES"] == 1
    assert config["PRINTBILLING_UPDATE_CHECK_INTERVAL"] == 3600
    assert config["PRINTBILLING_HEARTBEAT_INTERVAL"] == 60
    assert config["PRINTBILLING_QUEUE_ACTION_INTERVAL"] == 30


def test_silent_install_can_set_remote_spool_server():
    config = build_config(
        {},
        {},
        args(
            api_url="https://billing.example.com",
            username="agent",
            password="secret",
            organization="cliente-a",
            spool_server=r"\\SRV-PRINT01",
        ),
    )

    assert config["PRINTBILLING_SPOOL_SERVER"] == r"\\SRV-PRINT01"


def test_silent_install_can_set_log_level():
    config = build_config(
        {},
        {},
        args(
            api_url="https://billing.example.com",
            username="agent",
            password="secret",
            organization="cliente-a",
            log_level=" debug ",
        ),
    )

    assert config["PRINTBILLING_LOG_LEVEL"] == "DEBUG"


def test_silent_install_can_override_capture_and_update_flags():
    config = build_config(
        {},
        {},
        args(
            api_url="https://billing.example.com",
            username="agent",
            password="secret",
            organization="cliente-a",
            cancel_blocked="false",
            use_print_event_log="false",
            auto_update="false",
        ),
    )

    assert config["PRINTBILLING_CANCEL_BLOCKED"] is False
    assert config["PRINTBILLING_USE_PRINT_EVENT_LOG"] is False
    assert config["PRINTBILLING_AUTO_UPDATE"] is False


def test_silent_install_keeps_template_flags_when_not_overridden():
    template = {
        "PRINTBILLING_CANCEL_BLOCKED": False,
        "PRINTBILLING_USE_PRINT_EVENT_LOG": False,
        "PRINTBILLING_AUTO_UPDATE": False,
    }

    config = build_config(
        {},
        template,
        args(
            api_url="https://billing.example.com",
            username="agent",
            password="secret",
            organization="cliente-a",
        ),
    )

    assert config["PRINTBILLING_CANCEL_BLOCKED"] is False
    assert config["PRINTBILLING_USE_PRINT_EVENT_LOG"] is False
    assert config["PRINTBILLING_AUTO_UPDATE"] is False


def test_silent_install_ignores_empty_boolean_args_from_msi():
    existing = {
        "PRINTBILLING_API_URL": "https://billing.example.com",
        "PRINTBILLING_AGENT_USER": "agent",
        "PRINTBILLING_AGENT_PASSWORD": "secret",
        "PRINTBILLING_ORGANIZATION_SLUG": "cliente-a",
        "PRINTBILLING_CANCEL_BLOCKED": False,
        "PRINTBILLING_USE_PRINT_EVENT_LOG": False,
        "PRINTBILLING_AUTO_UPDATE": False,
    }

    config = build_config(
        existing,
        {},
        args(cancel_blocked="", use_print_event_log="", auto_update=""),
    )

    assert config["PRINTBILLING_CANCEL_BLOCKED"] is False
    assert config["PRINTBILLING_USE_PRINT_EVENT_LOG"] is False
    assert config["PRINTBILLING_AUTO_UPDATE"] is False


def test_silent_install_rejects_invalid_boolean_arg():
    try:
        build_config(
            {},
            {},
            args(
                api_url="https://billing.example.com",
                username="agent",
                password="secret",
                organization="cliente-a",
                auto_update="talvez",
            ),
        )
    except RuntimeError as exc:
        assert "booleano invalido" in str(exc)
    else:
        raise AssertionError("Valor booleano invalido deveria falhar")


def test_silent_install_rejects_invalid_log_level():
    try:
        build_config(
            {},
            {},
            args(
                api_url="https://billing.example.com",
                username="agent",
                password="secret",
                organization="cliente-a",
                log_level="verbose",
            ),
        )
    except RuntimeError as exc:
        assert "Modo de log invalido" in str(exc)
    else:
        raise AssertionError("Modo de log invalido deveria falhar")


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


def test_silent_install_rejects_known_unsafe_agent_password():
    try:
        build_config(
            {},
            {},
            args(
                api_url="https://billing.example.com",
                username="agent",
                password="agent12345",
                organization="cliente-a",
            ),
        )
    except RuntimeError as exc:
        assert "senha exclusiva" in str(exc).lower()
    else:
        raise AssertionError("Instalacao silenciosa nova nao deve aceitar senha padrao do agent")


def test_silent_reinstall_rejects_existing_unsafe_agent_password():
    existing = {
        "PRINTBILLING_API_URL": "https://billing.example.com",
        "PRINTBILLING_AGENT_USER": "agent",
        "PRINTBILLING_AGENT_PASSWORD": "change-me-agent-password",
        "PRINTBILLING_ORGANIZATION_SLUG": "cliente-a",
    }

    try:
        build_config(existing, {}, args())
    except RuntimeError as exc:
        assert "senha exclusiva" in str(exc).lower()
    else:
        raise AssertionError("Reinstalacao silenciosa nao deve preservar senha placeholder")
