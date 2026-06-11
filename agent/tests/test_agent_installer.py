import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_installer
from agent_installer import AGENT_EXE_NAME, CONFIG_NAME, build_config, install


def args(**overrides):
    values = {
        "silent": True,
        "api_url": None,
        "username": None,
        "password": None,
        "organization": None,
        "activation_key": None,
        "default_username": None,
        "spool_server": None,
        "snmp_community": None,
        "snmp_poll_interval": None,
        "snmp_timeout": None,
        "snmp_retries": None,
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


def test_silent_install_can_enroll_with_activation_key(monkeypatch):
    def fake_enroll(api_url, activation_key):
        assert api_url == "https://billing.example.com"
        assert activation_key == "pbk_cliente-a_token"
        return {
            "organization_slug": "cliente-a",
            "agent_username": "agent-pc-fin-123abc",
            "agent_password": "generated-secret",
        }

    monkeypatch.setattr(agent_installer, "enroll_with_activation_key", fake_enroll)

    config = build_config(
        {},
        {},
        args(
            api_url="https://billing.example.com/",
            activation_key="pbk_cliente-a_token",
            default_username="DIEGO LCD",
        ),
    )

    assert config["PRINTBILLING_API_URL"] == "https://billing.example.com"
    assert config["PRINTBILLING_AGENT_USER"] == "agent-pc-fin-123abc"
    assert config["PRINTBILLING_AGENT_PASSWORD"] == "generated-secret"
    assert config["PRINTBILLING_ORGANIZATION_SLUG"] == "cliente-a"
    assert config["PRINTBILLING_DEFAULT_USERNAME"] == "DIEGO LCD"


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


def test_silent_install_rejects_api_url_without_http_scheme():
    try:
        build_config(
            {},
            {},
            args(
                api_url="billing.example.com",
                username="agent",
                password="secret",
                organization="cliente-a",
            ),
        )
    except RuntimeError as exc:
        assert "URL da API invalida" in str(exc)
    else:
        raise AssertionError("Instalador nao deve aceitar URL sem http ou https")


def test_silent_install_normalizes_organization_slug():
    config = build_config(
        {},
        {},
        args(
            api_url="https://billing.example.com",
            username="agent",
            password="secret",
            organization=" Cliente-A ",
        ),
    )

    assert config["PRINTBILLING_ORGANIZATION_SLUG"] == "cliente-a"


def test_silent_install_rejects_invalid_organization_slug():
    try:
        build_config(
            {},
            {},
            args(
                api_url="https://billing.example.com",
                username="agent",
                password="secret",
                organization="cliente a",
            ),
        )
    except RuntimeError as exc:
        assert "Slug da empresa invalido" in str(exc)
    else:
        raise AssertionError("Instalador nao deve aceitar slug com espacos")


def test_silent_install_rejects_unsafe_agent_passwords():
    unsafe_passwords = (
        "",
        "admin",
        "agent",
        "admin12345",
        "agent12345",
        "change-me-agent-password",
        "change-me-admin-password",
        "password",
        "senha123",
        "12345678",
    )
    for password in unsafe_passwords:
        try:
            build_config(
                {},
                {},
                args(
                    api_url="https://billing.example.com",
                    username="agent",
                    password=password,
                    organization="cliente-a",
                ),
            )
        except RuntimeError as exc:
            assert "--password" in str(exc) or "senha exclusiva" in str(exc)
        else:
            raise AssertionError(f"Instalador nao deve aceitar senha insegura: {password!r}")


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


def test_silent_install_can_override_snmp_settings():
    config = build_config(
        {},
        {},
        args(
            api_url="https://billing.example.com",
            username="agent",
            password="secret",
            organization="cliente-a",
            snmp_community=" cliente-snmp ",
            snmp_poll_interval="120",
            snmp_timeout="3,5",
            snmp_retries="2",
        ),
    )

    assert config["PRINTBILLING_SNMP_COMMUNITY"] == "cliente-snmp"
    assert config["PRINTBILLING_SNMP_POLL_INTERVAL"] == 120
    assert config["PRINTBILLING_SNMP_TIMEOUT_SECONDS"] == 3.5
    assert config["PRINTBILLING_SNMP_RETRIES"] == 2


def test_silent_install_rejects_invalid_snmp_args():
    for overrides in (
        {"snmp_poll_interval": "0"},
        {"snmp_timeout": "0"},
        {"snmp_retries": "-1"},
    ):
        try:
            build_config(
                {},
                {},
                args(
                    api_url="https://billing.example.com",
                    username="agent",
                    password="secret",
                    organization="cliente-a",
                    **overrides,
                ),
            )
        except RuntimeError as exc:
            assert "SNMP" in str(exc) or "PRINTBILLING_SNMP" in str(exc)
        else:
            raise AssertionError(f"Argumento SNMP invalido deveria falhar: {overrides}")


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


def test_install_validates_config_before_removing_existing_service(monkeypatch, tmp_path):
    source_dir = tmp_path / "source"
    install_dir = tmp_path / "install"
    source_dir.mkdir()
    install_dir.mkdir()
    (source_dir / AGENT_EXE_NAME).write_text("new agent", encoding="utf-8")
    (source_dir / "config.json.example").write_text("{}", encoding="utf-8")
    target_exe = install_dir / AGENT_EXE_NAME
    target_exe.write_text("old agent", encoding="utf-8")
    (install_dir / CONFIG_NAME).write_text(
        json.dumps(
            {
                "PRINTBILLING_API_URL": "https://billing.example.com",
                "PRINTBILLING_AGENT_USER": "agent",
                "PRINTBILLING_AGENT_PASSWORD": "secret",
                "PRINTBILLING_ORGANIZATION_SLUG": "cliente-a",
            }
        ),
        encoding="utf-8",
    )
    stop_calls = []

    monkeypatch.setattr(agent_installer, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(agent_installer, "app_source_dir", lambda: source_dir)
    monkeypatch.setattr(agent_installer, "is_admin", lambda: True)
    monkeypatch.setattr(agent_installer, "stop_and_remove_existing_service", lambda path: stop_calls.append(path))

    try:
        install(args(organization="cliente invalido"))
    except RuntimeError as exc:
        assert "Slug da empresa invalido" in str(exc)
    else:
        raise AssertionError("Instalacao com slug invalido deveria falhar antes de remover o servico")

    assert stop_calls == []
    assert target_exe.read_text(encoding="utf-8") == "old agent"


def test_stop_and_remove_force_kills_stuck_service(monkeypatch, tmp_path):
    target_exe = tmp_path / AGENT_EXE_NAME
    target_exe.write_text("agent", encoding="utf-8")
    commands = []

    def fake_run(command, *, check=True, timeout=60):
        commands.append(command)
        stdout = "SERVICE_NAME: PrintBillingAgent\n        PID                : 4321\n" if command[:2] == ["sc.exe", "queryex"] else ""
        return agent_installer.subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(agent_installer, "run", fake_run)
    monkeypatch.setattr(agent_installer.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(agent_installer, "ensure_service_removed", lambda: None)

    agent_installer.stop_and_remove_existing_service(target_exe)

    assert ["taskkill.exe", "/PID", "4321", "/F", "/T"] in commands
    assert commands[-1] == ["sc.exe", "delete", agent_installer.SERVICE_NAME]


def test_stop_and_remove_reports_delete_pending_service(monkeypatch, tmp_path):
    target_exe = tmp_path / AGENT_EXE_NAME
    target_exe.write_text("agent", encoding="utf-8")

    def fake_run(command, *, check=True, timeout=60):
        return agent_installer.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(agent_installer, "run", fake_run)
    monkeypatch.setattr(agent_installer, "force_stop_service_if_running", lambda: None)
    monkeypatch.setattr(agent_installer, "wait_for_service_removed", lambda: False)
    monkeypatch.setattr(agent_installer.time, "sleep", lambda _seconds: None)

    try:
        agent_installer.stop_and_remove_existing_service(target_exe)
    except RuntimeError as exc:
        assert "marcado para exclusao" in str(exc)
        assert "reinicie o Windows" in str(exc)
    else:
        raise AssertionError("Servico marcado para exclusao deveria bloquear instalacao")


def test_ensure_service_running_rejects_stopped_service(monkeypatch):
    def fake_run(command, *, check=True, timeout=60):
        return agent_installer.subprocess.CompletedProcess(command, 0, stdout="STATE              : 1  STOPPED", stderr="")

    monkeypatch.setattr(agent_installer, "run", fake_run)

    try:
        agent_installer.ensure_service_running()
    except RuntimeError as exc:
        assert "nao entrou em execucao" in str(exc)
    else:
        raise AssertionError("Servico parado deveria falhar a instalacao")
