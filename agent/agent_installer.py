from __future__ import annotations

import ctypes
import getpass
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


SERVICE_NAME = "PrintBillingAgent"
INSTALL_DIR = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PrintBillingAgent"
AGENT_EXE_NAME = "PrintBillingAgent.exe"
CONFIG_NAME = "config.json"
EVENT_LOG_CHANNEL = "Microsoft-Windows-PrintService/Operational"
UNSAFE_AGENT_PASSWORDS = {
    "",
    "admin",
    "agent",
    "agent12345",
    "admin12345",
    "change-me-agent-password",
    "change-me-admin-password",
    "password",
    "senha123",
    "12345678",
}


def app_source_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).parent


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    executable = sys.executable
    params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    if result <= 32:
        raise RuntimeError("Nao foi possivel solicitar permissao de Administrador.")


def run(command: list[str], *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    print(f"> {' '.join(command)}")
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if check and result.returncode != 0:
        raise RuntimeError(f"Comando falhou com codigo {result.returncode}: {' '.join(command)}")
    return result


def prompt_value(label: str, default: str = "", secret: bool = False) -> str:
    if secret:
        suffix = " [manter senha atual]" if default else ""
        value = getpass.getpass(f"{label}{suffix}: ").strip()
    else:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip()
    return value or default


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pick_config_value(existing: dict, template: dict, key: str, default):
    if key in existing:
        return existing[key]
    if key in template:
        return template[key]
    return default


def pick_arg_or_config(arg_value, existing: dict, template: dict, key: str, default, *, allow_empty_arg: bool = False):
    if arg_value is not None and (allow_empty_arg or str(arg_value).strip()):
        return arg_value
    return pick_config_value(existing, template, key, default)


def pick_arg_or_existing(arg_value, existing: dict, key: str, default="", *, allow_empty_arg: bool = False):
    if arg_value is not None and (allow_empty_arg or str(arg_value).strip()):
        return arg_value
    return existing.get(key, default)


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    cleaned = str(value).strip().lower()
    if cleaned in {"true", "1", "yes", "sim"}:
        return True
    if cleaned in {"false", "0", "no", "nao", "não"}:
        return False
    raise RuntimeError(f"Valor booleano invalido: {value}")


def as_config_bool(value, default: bool) -> bool:
    try:
        return as_bool(value)
    except RuntimeError:
        return default


def as_config_int(value, default: int, *, min_value: int | None = None) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


def as_config_float(value, default: float, *, min_value: float | None = None) -> float:
    try:
        parsed = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


def as_int_arg(value, label: str, *, min_value: int | None = None) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} invalido: {value}") from exc
    if not math.isfinite(parsed):
        raise RuntimeError(f"{label} invalido: {value}")
    if min_value is not None and parsed < min_value:
        raise RuntimeError(f"{label} invalido: minimo {min_value}")
    return parsed


def as_float_arg(value, label: str, *, min_value: float | None = None) -> float:
    try:
        parsed = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} invalido: {value}") from exc
    if min_value is not None and parsed < min_value:
        raise RuntimeError(f"{label} invalido: minimo {min_value}")
    return parsed


def as_log_level(value, default: str = "INFO") -> str:
    cleaned = normalize_text(value).upper()
    if cleaned in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return cleaned
    if cleaned:
        raise RuntimeError(f"Modo de log invalido: {value}")
    return default


def pick_bool_arg_or_config(arg_value, existing: dict, template: dict, key: str, default: bool) -> bool:
    if arg_value is not None and str(arg_value).strip():
        return as_bool(arg_value)
    return as_config_bool(pick_config_value(existing, template, key, default), default)


def pick_int_arg_or_config(arg_value, existing: dict, template: dict, key: str, default: int, *, min_value: int | None = None) -> int:
    if arg_value is not None and str(arg_value).strip():
        return as_int_arg(arg_value, key, min_value=min_value)
    return as_config_int(pick_config_value(existing, template, key, default), default, min_value=min_value)


def pick_float_arg_or_config(arg_value, existing: dict, template: dict, key: str, default: float, *, min_value: float | None = None) -> float:
    if arg_value is not None and str(arg_value).strip():
        return as_float_arg(arg_value, key, min_value=min_value)
    return as_config_float(pick_config_value(existing, template, key, default), default, min_value=min_value)


def normalize_text(value) -> str:
    return str(value or "").strip()


def is_unsafe_agent_password(value: str) -> bool:
    return normalize_text(value).lower() in UNSAFE_AGENT_PASSWORDS


def normalize_api_url(value: str) -> str:
    cleaned = normalize_text(value).rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("URL da API invalida. Use http:// ou https:// com host da VPS.")
    return cleaned


def normalize_organization_slug(value: str) -> str:
    cleaned = normalize_text(value).lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*[a-z0-9]", cleaned):
        raise RuntimeError("Slug da empresa invalido. Use apenas letras, numeros e hifens, sem espacos.")
    return cleaned


def computer_name() -> str:
    return normalize_text(os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "")


def enroll_with_activation_key(api_url: str, activation_key: str) -> dict:
    import requests

    response = requests.post(
        f"{api_url}/agent/enroll",
        json={"enrollment_key": normalize_text(activation_key), "computer_name": computer_name() or None},
        timeout=20,
    )
    if response.status_code >= 400:
        detail = response.text[:500]
        raise RuntimeError(f"Chave de ativacao recusada pela API ({response.status_code}): {detail}")
    data = response.json()
    required = {"organization_slug", "agent_username", "agent_password"}
    missing = [key for key in required if not normalize_text(data.get(key))]
    if missing:
        raise RuntimeError(f"Resposta de ativacao incompleta: {', '.join(missing)}")
    return data


def build_config(existing: dict, template: dict, args: argparse.Namespace) -> dict:
    activation_key = normalize_text(getattr(args, "activation_key", ""))
    if args.silent:
        api_url = pick_arg_or_existing(args.api_url, existing, "PRINTBILLING_API_URL", "")
        if activation_key:
            api_url = normalize_api_url(api_url)
            enrollment = enroll_with_activation_key(api_url, activation_key)
            username = enrollment["agent_username"]
            password = enrollment["agent_password"]
            organization_slug = enrollment["organization_slug"]
        else:
            username = pick_arg_or_existing(args.username, existing, "PRINTBILLING_AGENT_USER", "")
            password = pick_arg_or_existing(args.password, existing, "PRINTBILLING_AGENT_PASSWORD", "")
            organization_slug = pick_arg_or_existing(args.organization, existing, "PRINTBILLING_ORGANIZATION_SLUG", "")
        default_username = pick_arg_or_config(
            args.default_username,
            existing,
            template,
            "PRINTBILLING_DEFAULT_USERNAME",
            "",
            allow_empty_arg=True,
        )
        spool_server = pick_arg_or_config(args.spool_server, existing, template, "PRINTBILLING_SPOOL_SERVER", "")
        snmp_community = pick_arg_or_config(args.snmp_community, existing, template, "PRINTBILLING_SNMP_COMMUNITY", "public")
        snmp_poll_interval = pick_int_arg_or_config(args.snmp_poll_interval, existing, template, "PRINTBILLING_SNMP_POLL_INTERVAL", 60, min_value=1)
        snmp_timeout = pick_float_arg_or_config(args.snmp_timeout, existing, template, "PRINTBILLING_SNMP_TIMEOUT_SECONDS", 2.0, min_value=0.1)
        snmp_retries = pick_int_arg_or_config(args.snmp_retries, existing, template, "PRINTBILLING_SNMP_RETRIES", 1, min_value=0)
        cancel_blocked = pick_bool_arg_or_config(args.cancel_blocked, existing, template, "PRINTBILLING_CANCEL_BLOCKED", True)
        use_print_event_log = pick_bool_arg_or_config(args.use_print_event_log, existing, template, "PRINTBILLING_USE_PRINT_EVENT_LOG", True)
        auto_update = pick_bool_arg_or_config(args.auto_update, existing, template, "PRINTBILLING_AUTO_UPDATE", True)
        log_level = as_log_level(pick_arg_or_config(args.log_level, existing, template, "PRINTBILLING_LOG_LEVEL", "INFO"))
        if not activation_key and (not api_url or not username or not password or not organization_slug):
            raise RuntimeError("Modo silencioso requer --api-url com --activation-key, ou --api-url, --username, --password e --organization.")
    else:
        print()
        print("Configuracao do Agent")
        print("Pressione Enter para manter o valor sugerido.")

        api_url = prompt_value(
            "URL da API na VPS",
            existing.get("PRINTBILLING_API_URL") or template.get("PRINTBILLING_API_URL", ""),
        )
        activation_key = prompt_value("Chave de ativacao da empresa (recomendado; deixe vazio para modo avancado)", "")
        if activation_key:
            api_url = normalize_api_url(api_url)
            enrollment = enroll_with_activation_key(api_url, activation_key)
            username = enrollment["agent_username"]
            password = enrollment["agent_password"]
            organization_slug = enrollment["organization_slug"]
            print(f"Ativacao concluida para empresa: {organization_slug}")
        else:
            username = prompt_value(
                "Usuario tecnico do agent",
                existing.get("PRINTBILLING_AGENT_USER") or template.get("PRINTBILLING_AGENT_USER", "agent"),
            )
            password = prompt_value(
                "Senha do usuario tecnico",
                existing.get("PRINTBILLING_AGENT_PASSWORD") or template.get("PRINTBILLING_AGENT_PASSWORD", ""),
                secret=True,
            )
            organization_slug = prompt_value(
                "Slug da empresa",
                existing.get("PRINTBILLING_ORGANIZATION_SLUG") or template.get("PRINTBILLING_ORGANIZATION_SLUG", "default"),
            )
        default_username = prompt_value(
            "Usuario padrao deste PC, se o Windows nao informar",
            existing.get("PRINTBILLING_DEFAULT_USERNAME") or template.get("PRINTBILLING_DEFAULT_USERNAME", ""),
        )
        spool_server = prompt_value(
            "Servidor de impressao remoto (opcional)",
            existing.get("PRINTBILLING_SPOOL_SERVER") or template.get("PRINTBILLING_SPOOL_SERVER", ""),
        )
        snmp_community = prompt_value(
            "Comunidade SNMP",
            existing.get("PRINTBILLING_SNMP_COMMUNITY") or template.get("PRINTBILLING_SNMP_COMMUNITY", "public"),
        )
        snmp_poll_interval = as_config_int(pick_config_value(existing, template, "PRINTBILLING_SNMP_POLL_INTERVAL", 60), 60, min_value=1)
        snmp_timeout = as_config_float(pick_config_value(existing, template, "PRINTBILLING_SNMP_TIMEOUT_SECONDS", 2.0), 2.0, min_value=0.1)
        snmp_retries = as_config_int(pick_config_value(existing, template, "PRINTBILLING_SNMP_RETRIES", 1), 1, min_value=0)
        log_level = as_log_level(
            prompt_value(
                "Modo de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
                existing.get("PRINTBILLING_LOG_LEVEL") or template.get("PRINTBILLING_LOG_LEVEL", "INFO"),
            )
        )
        cancel_blocked = as_config_bool(pick_config_value(existing, template, "PRINTBILLING_CANCEL_BLOCKED", True), True)
        use_print_event_log = as_config_bool(pick_config_value(existing, template, "PRINTBILLING_USE_PRINT_EVENT_LOG", True), True)
        auto_update = as_config_bool(pick_config_value(existing, template, "PRINTBILLING_AUTO_UPDATE", True), True)

    api_url = normalize_api_url(api_url)
    username = normalize_text(username)
    password = normalize_text(password)
    organization_slug = normalize_organization_slug(organization_slug)
    default_username = normalize_text(default_username)
    spool_server = normalize_text(spool_server)
    snmp_community = normalize_text(snmp_community) or "public"
    log_level = as_log_level(log_level)
    if not username or not password:
        raise RuntimeError("Configuracao do agent requer API URL, usuario, senha e slug da empresa.")
    if is_unsafe_agent_password(password):
        raise RuntimeError("Senha do usuario tecnico do agent e insegura. Gere uma senha exclusiva para esta empresa.")

    return {
        "PRINTBILLING_API_URL": api_url,
        "PRINTBILLING_AGENT_USER": username,
        "PRINTBILLING_AGENT_PASSWORD": password,
        "PRINTBILLING_ORGANIZATION_SLUG": organization_slug,
        "PRINTBILLING_CANCEL_BLOCKED": cancel_blocked,
        "PRINTBILLING_POLL_INTERVAL": as_config_int(pick_config_value(existing, template, "PRINTBILLING_POLL_INTERVAL", 5), 5, min_value=1),
        "PRINTBILLING_DEFAULT_USERNAME": default_username,
        "PRINTBILLING_SNMP_POLL_INTERVAL": snmp_poll_interval,
        "PRINTBILLING_SNMP_COMMUNITY": snmp_community,
        "PRINTBILLING_SNMP_TIMEOUT_SECONDS": snmp_timeout,
        "PRINTBILLING_SNMP_RETRIES": snmp_retries,
        "PRINTBILLING_USE_PRINT_EVENT_LOG": use_print_event_log,
        "PRINTBILLING_AUTO_UPDATE": auto_update,
        "PRINTBILLING_UPDATE_CHECK_INTERVAL": as_config_int(pick_config_value(existing, template, "PRINTBILLING_UPDATE_CHECK_INTERVAL", 3600), 3600, min_value=60),
        "PRINTBILLING_HEARTBEAT_INTERVAL": as_config_int(pick_config_value(existing, template, "PRINTBILLING_HEARTBEAT_INTERVAL", 60), 60, min_value=10),
        "PRINTBILLING_QUEUE_ACTION_INTERVAL": as_config_int(pick_config_value(existing, template, "PRINTBILLING_QUEUE_ACTION_INTERVAL", 30), 30, min_value=5),
        "PRINTBILLING_SPOOL_SERVER": spool_server,
        "PRINTBILLING_LOG_LEVEL": log_level,
    }


def stop_and_remove_existing_service(target_exe: Path) -> None:
    if target_exe.exists():
        run([str(target_exe), "stop"], check=False, timeout=30)
        run([str(target_exe), "remove"], check=False, timeout=30)
    run(["sc.exe", "stop", SERVICE_NAME], check=False, timeout=30)
    run(["sc.exe", "delete", SERVICE_NAME], check=False, timeout=30)
    time.sleep(2)


def install(args: argparse.Namespace) -> None:
    if not is_admin():
        print("Solicitando permissao de Administrador...")
        relaunch_as_admin()
        return

    source_dir = app_source_dir()
    bundled_agent = source_dir / AGENT_EXE_NAME
    bundled_template = source_dir / "config.json.example"
    if not bundled_agent.exists():
        raise FileNotFoundError(f"Arquivo interno nao encontrado: {AGENT_EXE_NAME}")

    target_exe = INSTALL_DIR / AGENT_EXE_NAME
    target_config = INSTALL_DIR / CONFIG_NAME
    template = load_json(bundled_template)
    existing = load_json(target_config)
    config = build_config(existing, template, args)

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    print("Parando/removendo servico anterior...")
    stop_and_remove_existing_service(target_exe)

    print("Copiando arquivos do agent...")
    shutil.copy2(bundled_agent, target_exe)

    target_config.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print("Habilitando log operacional de impressao do Windows...")
    run(["wevtutil.exe", "sl", EVENT_LOG_CHANNEL, "/e:true"], check=False, timeout=30)

    print("Instalando servico...")
    run([str(target_exe), "--startup", "auto", "install"], timeout=60)

    print("Iniciando servico...")
    run([str(target_exe), "start"], timeout=60)

    print()
    print("Instalacao concluida.")
    print(f"Pasta: {INSTALL_DIR}")
    print(f"Log: {INSTALL_DIR / 'agent.log'}")
    print()
    print("Faca uma impressao nova e confira se aparece no sistema.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Instalador do PrintBilling Agent")
    parser.add_argument("--silent", action="store_true", help="Instala sem prompts interativos")
    parser.add_argument("--api-url", help="URL da API na VPS")
    parser.add_argument("--username", help="Usuario tecnico do agent")
    parser.add_argument("--password", help="Senha do usuario tecnico")
    parser.add_argument("--organization", help="Slug da empresa")
    parser.add_argument("--activation-key", help="Chave de ativacao da empresa para configurar o agent sem expor credenciais")
    parser.add_argument("--default-username", help="Usuario padrao quando o Windows nao informar")
    parser.add_argument("--spool-server", help="Servidor de impressao remoto opcional para enumerar filas")
    parser.add_argument("--snmp-community", help="Comunidade SNMP usada para monitorar impressoras de rede")
    parser.add_argument("--snmp-poll-interval", help="Intervalo de coleta SNMP em segundos")
    parser.add_argument("--snmp-timeout", help="Timeout SNMP em segundos")
    parser.add_argument("--snmp-retries", help="Numero de tentativas SNMP")
    parser.add_argument("--log-level", help="Modo de log: DEBUG, INFO, WARNING, ERROR ou CRITICAL")
    parser.add_argument("--cancel-blocked", help="Cancela trabalhos bloqueados no spool: true ou false")
    parser.add_argument("--use-print-event-log", help="Usa Event Log de impressao do Windows: true ou false")
    parser.add_argument("--auto-update", help="Permite auto-update do agent: true ou false")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        install(args)
    except Exception as exc:
        print()
        print(f"[ERRO] {exc}")
        if not args.silent:
            input("Pressione Enter para sair...")
        raise
    if not args.silent:
        input("Pressione Enter para sair...")


if __name__ == "__main__":
    main()
