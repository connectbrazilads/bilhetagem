import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import organization_allows_access, require_roles
from app.models.agent_queue_action import AgentQueueAction, AgentQueueActionStatus, AgentQueueActionType
from app.models.agent_log import AgentLog
from app.models.organization import Organization
from app.models.print_agent import PrintAgent
from app.models.print_job import PrintJob
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User
from app.models.user import UserRole
from app.schemas.agent import (
    AgentDeploymentOrganizationRead,
    AgentHeartbeatPayload,
    AgentHealthAlertRead,
    AgentLogRead,
    AgentQueuePayload,
    AgentQueueRead,
    AgentQueueBulkActionCreate,
    AgentReleaseFileRead,
    AgentReleaseRead,
    AgentQueueActionCreate,
    AgentQueueActionRead,
    AgentQueueActionResult,
    AgentRecentJobRead,
    AgentVersionRead,
    PrintAgentRead,
)
from app.services.audit_service import write_audit
from app.services.agent_release_service import is_newer_version, published_agent_update_version, version_tuple
from app.services.organization_service import DEFAULT_ORGANIZATION_SLUG
from app.services.printer_identity_service import conflicting_alias_ids

router = APIRouter(prefix="/agent", tags=["agent"])
QUEUE_ACTION_STALE_AFTER = timedelta(minutes=15)
RECENT_AGENT_LOG_ALERT_WINDOW = timedelta(minutes=15)
AGENT_LOG_RETENTION = timedelta(days=7)
AGENT_LOG_MAX_PER_AGENT = 200
ACTIVE_QUEUE_ACTION_STATUSES = (AgentQueueActionStatus.pending, AgentQueueActionStatus.running)


def _agent_file() -> Path:
    return Path(settings.agent_download_dir) / settings.agent_download_filename


def _publishable_file_size(path: Path) -> int | None:
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
    except OSError:
        return None
    return size if size > 0 else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path() -> Path:
    return Path(settings.agent_download_dir) / settings.agent_release_manifest_filename


def _release_file(version: str, filename: str) -> Path:
    root = Path(settings.agent_download_dir)
    versioned = root / version / filename
    if versioned.exists():
        return versioned
    return root / filename


def _is_safe_release_filename(filename: str) -> bool:
    return bool(filename) and Path(filename).name == filename and "/" not in filename and "\\" not in filename


def _is_safe_release_version(version: str) -> bool:
    return bool(version) and Path(version).name == version and "/" not in version and "\\" not in version


def _manifest_str(value, default: str | None = None) -> str | None:
    if value is None:
        return default
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return text or default
    return default


def _manifest_sha256(value) -> str | None:
    expected = _manifest_str(value)
    if not expected:
        return None
    expected = expected.lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        return ""
    return expected


def _manifest_int(value) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _published_release_checksums(version: str) -> dict[str, str] | None:
    path = _release_file(version, "SHA256SUMS.txt")
    if not path.is_file():
        return None
    checksums: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        parts = trimmed.split(None, 1)
        if len(parts) != 2:
            return {}
        checksum = _manifest_sha256(parts[0])
        filename = parts[1].strip().lstrip("*")
        if not checksum or not _is_safe_release_filename(filename):
            return {}
        if filename in checksums and checksums[filename] != checksum:
            return {}
        checksums[filename] = checksum
    return checksums


def _manifest_release_filenames(raw_files: list) -> set[str]:
    filenames: set[str] = set()
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        filename = str(raw_file.get("filename") or "")
        if _is_safe_release_filename(filename):
            filenames.add(filename)
    return filenames


def _release_signature_summary(files: list[AgentReleaseFileRead]) -> tuple[str, str]:
    if not files:
        return "empty", "Nenhum arquivo publicado"
    statuses = [(file.signature_status or "NotSigned") for file in files]
    valid_count = sum(1 for status in statuses if status == "Valid")
    unsigned_count = sum(1 for status in statuses if status == "NotSigned")
    if valid_count == len(statuses):
        return "signed", "Todos os artefatos estao assinados"
    if unsigned_count == len(statuses):
        return "unsigned", "Artefatos sem assinatura digital"
    if valid_count > 0 and valid_count + unsigned_count == len(statuses):
        return "mixed", "Assinatura parcial: nem todos os artefatos estao assinados"
    return "invalid", "Ha artefatos com assinatura invalida ou status inesperado"


def _load_release_manifest() -> list[AgentReleaseRead]:
    manifest_path = _manifest_path()
    releases: list[AgentReleaseRead] = []
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
    else:
        data = None

    if isinstance(data, dict):
        for raw_release in data.get("versions", []):
            if not isinstance(raw_release, dict):
                continue
            version = str(raw_release.get("version") or "")
            if not _is_safe_release_version(version):
                continue
            files = []
            raw_files = raw_release.get("files", [])
            if not isinstance(raw_files, list):
                raw_files = []
            published_checksums = _published_release_checksums(version)
            checksums_mismatch = (
                published_checksums is not None
                and set(published_checksums) != _manifest_release_filenames(raw_files)
            )
            for raw_file in raw_files:
                if not isinstance(raw_file, dict):
                    continue
                filename = str(raw_file.get("filename") or "")
                if not _is_safe_release_filename(filename):
                    continue
                if checksums_mismatch:
                    continue
                path = _release_file(version, filename)
                actual_size = _publishable_file_size(path)
                if actual_size is None:
                    continue
                actual_sha256 = _sha256(path)
                expected_sha256 = _manifest_sha256(raw_file.get("sha256"))
                expected_size = _manifest_int(raw_file.get("size_bytes"))
                expected_published_sha256 = published_checksums.get(filename) if published_checksums is not None else None
                if expected_published_sha256 is not None and expected_published_sha256 != actual_sha256:
                    continue
                if expected_sha256 is not None and expected_sha256 != actual_sha256:
                    continue
                if expected_size is not None and expected_size != actual_size:
                    continue
                files.append(
                    AgentReleaseFileRead(
                        kind=str(raw_file.get("kind") or "agent"),
                        filename=filename,
                        size_bytes=actual_size,
                        sha256=actual_sha256,
                        signature_status=_manifest_str(raw_file.get("signature_status")),
                        signer_subject=_manifest_str(raw_file.get("signer_subject")),
                        download_url=f"/agent/releases/{version}/download?filename={filename}",
                    )
                )
            signature_status, signature_summary = _release_signature_summary(files)
            releases.append(
                AgentReleaseRead(
                    version=version,
                    channel=_manifest_str(raw_release.get("channel"), "stable") or "stable",
                    published_at=_manifest_str(raw_release.get("published_at")),
                    notes=_manifest_str(raw_release.get("notes")),
                    checksums_url=f"/agent/releases/{version}/checksums",
                    checksums_sha256=_release_checksums_sha256_for_files(files),
                    signature_status=signature_status,
                    signature_summary=signature_summary,
                    files=files,
                )
            )
        return sorted(releases, key=_release_sort_key, reverse=True)

    path = _agent_file()
    legacy_size = _publishable_file_size(path)
    if legacy_size is not None:
        files = [
            AgentReleaseFileRead(
                kind="agent",
                filename=path.name,
                size_bytes=legacy_size,
                sha256=_sha256(path),
                signature_status=None,
                signer_subject=None,
                download_url="/agent/download",
            )
        ]
        releases.append(
            AgentReleaseRead(
                version=settings.agent_latest_version,
                checksums_url=f"/agent/releases/{settings.agent_latest_version}/checksums",
                checksums_sha256=_release_checksums_sha256_for_files(files),
                signature_status="unsigned",
                signature_summary="Artefato legado sem assinatura registrada no manifest",
                files=files,
            )
        )
    return releases


def _release_sort_key(release: AgentReleaseRead) -> tuple[str, tuple[int, ...]]:
    return (release.published_at or "", version_tuple(release.version))


def _latest_agent_release_file() -> tuple[AgentReleaseRead, AgentReleaseFileRead] | None:
    for release in _load_release_manifest():
        for file in release.files:
            if file.kind == "agent":
                return release, file
    return None


def _release_or_404(version: str) -> AgentReleaseRead:
    if not _is_safe_release_version(version):
        raise HTTPException(status_code=400, detail="Versao invalida")
    releases = {release.version: release for release in _load_release_manifest()}
    release = releases.get(version)
    if not release:
        raise HTTPException(status_code=404, detail="Versao nao encontrada")
    return release


def _release_checksums_text_for_files(files: list[AgentReleaseFileRead]) -> str:
    lines = [f"{file.sha256}  {file.filename}" for file in sorted(files, key=lambda item: item.filename.lower())]
    return "\n".join(lines) + ("\n" if lines else "")


def _release_checksums_sha256_for_files(files: list[AgentReleaseFileRead]) -> str | None:
    content = _release_checksums_text_for_files(files)
    return hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None


def _release_checksums_text(release: AgentReleaseRead) -> str:
    return _release_checksums_text_for_files(release.files)


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _identity_key(value: str | None) -> str | None:
    cleaned = _clean_optional(value)
    return cleaned.lower() if cleaned else None


def _same_identity(left: str | None, right: str | None) -> bool:
    left_key = _identity_key(left)
    right_key = _identity_key(right)
    return bool(left_key and right_key and left_key == right_key)


def _find_printer_by_serial(db: Session, organization_id: int, serial_number: str | None) -> Printer | None:
    identity = _identity_key(serial_number)
    if not identity:
        return None
    return (
        db.query(Printer)
        .filter(
            Printer.organization_id == organization_id,
            Printer.serial_number.isnot(None),
            func.lower(Printer.serial_number) == identity,
        )
        .first()
    )


def _find_alias_by_identity(db: Session, organization_id: int, column, value: str | None, *, require_printer: bool = False) -> PrinterAlias | None:
    identity = _identity_key(value)
    if not identity:
        return None
    filters = [
        PrinterAlias.organization_id == organization_id,
        column.isnot(None),
        func.lower(column) == identity,
    ]
    if require_printer:
        filters.append(PrinterAlias.printer_id.isnot(None))
    return db.query(PrinterAlias).filter(*filters).first()


def _normalize_alias_name(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.strip().lower().split()) or None


def _plain_text_key(value: str | None) -> str | None:
    cleaned = _clean_optional(value)
    if not cleaned:
        return None
    normalized = unicodedata.normalize("NFKD", cleaned)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(ascii_text.lower().split()) or None


def _is_generic_queue_name(value: str | None) -> bool:
    return _plain_text_key(value) in {
        "documento de impressao",
        "print document",
        "user",
        "unknown",
    }


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()[:45] or None
    if request.client:
        return request.client.host[:45]
    return None


def _agent_status(agent: PrintAgent, now: datetime | None = None) -> tuple[bool, str]:
    if not agent.last_seen_at:
        return False, "Nunca conectado"
    now = now or datetime.now(timezone.utc)
    last_seen = agent.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    if now - last_seen <= timedelta(minutes=3):
        if agent.last_error:
            return True, "Online com alerta"
        return True, "Online"
    return False, "Offline"


def _can_manage_all_organizations(actor: User) -> bool:
    return bool(actor.organization and actor.organization.slug == DEFAULT_ORGANIZATION_SLUG and actor.role == UserRole.admin)


def _recent_jobs(db: Session, agent: PrintAgent) -> list[AgentRecentJobRead]:
    jobs = (
        db.query(PrintJob)
        .filter(PrintJob.organization_id == agent.organization_id, PrintJob.agent_id == agent.id)
        .order_by(PrintJob.submitted_at.desc(), PrintJob.id.desc())
        .limit(10)
        .all()
    )
    return [
        AgentRecentJobRead(
            id=job.id,
            username=job.user.username if job.user else "-",
            printer_name=job.printer.name if job.printer else job.queue_name or "-",
            document_name=job.document_name,
            pages=job.pages,
            is_color=job.is_color,
            status=job.status.value if hasattr(job.status, "value") else str(job.status),
            policy_name=job.policy_name,
            policy_action=job.policy_action,
            submitted_at=job.submitted_at,
        )
        for job in jobs
    ]


def _recent_logs(db: Session, agent: PrintAgent) -> list[AgentLogRead]:
    logs = (
        db.query(AgentLog)
        .filter(AgentLog.organization_id == agent.organization_id, AgentLog.agent_id == agent.id)
        .order_by(AgentLog.occurred_at.desc(), AgentLog.id.desc())
        .limit(50)
        .all()
    )
    return [AgentLogRead.model_validate(log) for log in logs]


def _store_agent_logs(db: Session, agent: PrintAgent, payload: AgentHeartbeatPayload, received_at: datetime) -> None:
    allowed_levels = {"debug", "info", "warning", "error", "critical"}
    new_logs: list[AgentLog] = []
    for item in payload.logs:
        level = (item.level or "info").strip().lower()
        if level not in allowed_levels:
            level = "info"
        message = item.message.strip()
        if not message:
            continue
        new_logs.append(
            AgentLog(
                organization_id=agent.organization_id,
                agent_id=agent.id,
                level=level,
                message=message[:1000],
                source=_clean_optional(item.source),
                occurred_at=item.occurred_at or received_at,
                received_at=received_at,
            )
        )
    if new_logs:
        db.add_all(new_logs)
        db.flush()
    _prune_agent_logs(db, agent, received_at)


def _prune_agent_logs(db: Session, agent: PrintAgent, received_at: datetime) -> None:
    cutoff = received_at - AGENT_LOG_RETENTION
    db.query(AgentLog).filter(
        AgentLog.organization_id == agent.organization_id,
        AgentLog.agent_id == agent.id,
        AgentLog.received_at < cutoff,
    ).delete(synchronize_session=False)

    stale_ids = [
        row[0]
        for row in (
            db.query(AgentLog.id)
            .filter(AgentLog.organization_id == agent.organization_id, AgentLog.agent_id == agent.id)
            .order_by(AgentLog.occurred_at.desc(), AgentLog.id.desc())
            .offset(AGENT_LOG_MAX_PER_AGENT)
            .all()
        )
    ]
    if stale_ids:
        db.query(AgentLog).filter(AgentLog.id.in_(stale_ids)).delete(synchronize_session=False)


def _recent_error_log_alert(db: Session, agent: PrintAgent) -> AgentHealthAlertRead | None:
    since = datetime.now(timezone.utc) - RECENT_AGENT_LOG_ALERT_WINDOW
    logs = (
        db.query(AgentLog)
        .filter(
            AgentLog.organization_id == agent.organization_id,
            AgentLog.agent_id == agent.id,
            AgentLog.received_at >= since,
            AgentLog.level.in_(["error", "critical"]),
        )
        .order_by(AgentLog.received_at.desc(), AgentLog.id.desc())
        .limit(20)
        .all()
    )
    if not logs:
        return None
    latest = logs[0]
    severity = "error" if any(log.level == "critical" for log in logs) else "warning"
    return AgentHealthAlertRead(
        code="recent_error_logs",
        severity=severity,
        message=f"{len(logs)} log(s) de erro nos ultimos 15 min: {latest.message[:140]}",
    )


def _agent_health_alerts(
    agent: PrintAgent,
    is_online: bool,
    db: Session | None = None,
    conflict_alias_ids: set[int] | None = None,
) -> list[AgentHealthAlertRead]:
    alerts: list[AgentHealthAlertRead] = []
    aliases = list(agent.aliases)
    present_aliases = [alias for alias in aliases if _alias_is_present(agent, alias)]
    stale_queues = [alias.queue_name for alias in aliases if not _alias_is_present(agent, alias)]
    unbound_queues = [alias.queue_name for alias in present_aliases if alias.printer_id is None]
    duplicate_queues = _duplicate_present_queue_aliases(present_aliases)
    generic_queues = [alias.queue_name for alias in present_aliases if _is_generic_queue_name(alias.queue_name)]
    weak_identity_queues = _weak_identity_queue_aliases(present_aliases)
    identity_conflict_queues = [
        alias.queue_name
        for alias in present_aliases
        if conflict_alias_ids is not None and alias.id in conflict_alias_ids
    ]
    stale_actions = _stale_queue_actions(agent)

    if not is_online:
        alerts.append(AgentHealthAlertRead(code="offline", severity="error", message="Agent offline ou sem contato recente"))
    if agent.last_error:
        alerts.append(AgentHealthAlertRead(code="last_error", severity="warning", message=agent.last_error))
    if db is not None:
        recent_error_alert = _recent_error_log_alert(db, agent)
        if recent_error_alert:
            alerts.append(recent_error_alert)
    if agent.event_log_enabled is False:
        alerts.append(AgentHealthAlertRead(code="event_log_disabled", severity="warning", message="Event Log de impressao desativado no agent"))
    if agent.local_admin is False:
        alerts.append(
            AgentHealthAlertRead(
                code="local_admin_missing",
                severity="warning",
                message="Agent sem privilegio administrativo local; acoes remotas e controle de filas podem falhar",
            )
        )
    if agent.last_seen_at and not present_aliases:
        alerts.append(AgentHealthAlertRead(code="no_queues", severity="warning", message="Nenhuma fila local detectada no ultimo heartbeat"))
    if stale_queues:
        count = len(stale_queues)
        sample = ", ".join(stale_queues[:3])
        suffix = f": {sample}" if sample else ""
        alerts.append(AgentHealthAlertRead(code="stale_queues", severity="warning", message=f"{count} fila(s) nao detectada(s) no ultimo heartbeat{suffix}"))
    if unbound_queues:
        count = len(unbound_queues)
        sample = ", ".join(unbound_queues[:3])
        suffix = f": {sample}" if sample else ""
        alerts.append(AgentHealthAlertRead(code="unbound_queues", severity="warning", message=f"{count} fila(s) sem vinculo com impressora fisica{suffix}"))
    if duplicate_queues:
        count = len(duplicate_queues)
        sample = ", ".join(duplicate_queues[:3])
        suffix = f": {sample}" if sample else ""
        alerts.append(AgentHealthAlertRead(code="duplicate_queue_aliases", severity="warning", message=f"{count} fila(s) duplicada(s) por nome normalizado{suffix}"))
    if generic_queues:
        count = len(generic_queues)
        sample = ", ".join(generic_queues[:3])
        suffix = f": {sample}" if sample else ""
        alerts.append(AgentHealthAlertRead(code="generic_queue_names", severity="warning", message=f"{count} fila(s) com nome generico; padronize ou vincule a fila correta{suffix}"))
    if weak_identity_queues:
        count = len(weak_identity_queues)
        sample = ", ".join(weak_identity_queues[:3])
        suffix = f": {sample}" if sample else ""
        alerts.append(
            AgentHealthAlertRead(
                code="weak_queue_identity",
                severity="warning",
                message=f"{count} fila(s) sem serial/IP/device confiavel; revise metadata para evitar duplicidade{suffix}",
            )
        )
    if identity_conflict_queues:
        count = len(identity_conflict_queues)
        sample = ", ".join(identity_conflict_queues[:3])
        suffix = f": {sample}" if sample else ""
        alerts.append(
            AgentHealthAlertRead(
                code="hardware_identity_conflict",
                severity="warning",
                message=f"{count} fila(s) com serial/IP/device/fingerprint vinculado a mais de uma impressora{suffix}",
            )
        )
    if stale_actions:
        count = len(stale_actions)
        sample = ", ".join(action.queue_name for action in stale_actions[:3])
        suffix = f": {sample}" if sample else ""
        alerts.append(AgentHealthAlertRead(code="stale_queue_actions", severity="warning", message=f"{count} acao(oes) remota(s) sem conclusao ha mais de 15 min{suffix}"))
    latest_version = published_agent_update_version()
    if latest_version and is_newer_version(latest_version, agent.version):
        alerts.append(AgentHealthAlertRead(code="outdated_version", severity="info", message=f"Agent abaixo da versao publicada {latest_version}"))
        if agent.auto_update_enabled is False:
            alerts.append(
                AgentHealthAlertRead(
                    code="auto_update_disabled",
                    severity="warning",
                    message="Auto-update desativado neste agent; atualize manualmente ou reinstale com auto-update ativo",
                )
            )

    return alerts


def _duplicate_present_queue_aliases(aliases: list[PrinterAlias]) -> list[str]:
    grouped: dict[tuple[int | None, str], list[str]] = {}
    for alias in aliases:
        normalized = alias.normalized_queue_name or _normalize_alias_name(alias.queue_name)
        if not normalized:
            continue
        grouped.setdefault((alias.agent_id, normalized), []).append(alias.queue_name)
    duplicates: list[str] = []
    for names in grouped.values():
        if len(names) > 1:
            duplicates.extend(names[1:])
    return duplicates


def _weak_identity_queue_aliases(aliases: list[PrinterAlias]) -> list[str]:
    weak: list[str] = []
    for alias in aliases:
        fingerprint = (alias.fingerprint or "").strip().lower()
        has_strong_identity = bool(alias.serial_number or alias.ip_address or alias.device_id) or fingerprint.startswith(
            ("serial:", "ip:", "device:", "usb:", "network:")
        )
        if not has_strong_identity:
            weak.append(alias.queue_name)
    return weak


def _stale_queue_actions(agent: PrintAgent) -> list[AgentQueueAction]:
    now = datetime.now(timezone.utc)
    stale: list[AgentQueueAction] = []
    for action in agent.queue_actions:
        if action.status not in (AgentQueueActionStatus.pending, AgentQueueActionStatus.running):
            continue
        reference = action.dispatched_at if action.status == AgentQueueActionStatus.running else action.requested_at
        if reference is None:
            continue
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        if now - reference > QUEUE_ACTION_STALE_AFTER:
            stale.append(action)
    return stale


def _alias_is_present(agent: PrintAgent, alias: PrinterAlias) -> bool:
    if not agent.last_seen_at or not alias.last_seen_at:
        return False
    agent_seen = agent.last_seen_at
    alias_seen = alias.last_seen_at
    if agent_seen.tzinfo is None:
        agent_seen = agent_seen.replace(tzinfo=timezone.utc)
    if alias_seen.tzinfo is None:
        alias_seen = alias_seen.replace(tzinfo=timezone.utc)
    return alias_seen >= agent_seen


def _alias_to_read(agent: PrintAgent, alias: PrinterAlias) -> AgentQueueRead:
    return AgentQueueRead(
        id=alias.id,
        printer_id=alias.printer_id,
        queue_name=alias.queue_name,
        computer_name=alias.computer_name,
        driver_name=alias.driver_name,
        port_name=alias.port_name,
        connection_type=alias.connection_type,
        ip_address=alias.ip_address,
        serial_number=alias.serial_number,
        device_id=alias.device_id,
        fingerprint=alias.fingerprint,
        last_seen_at=alias.last_seen_at,
        is_present=_alias_is_present(agent, alias),
    )


def _agent_to_read(
    agent: PrintAgent,
    include_jobs: bool = False,
    db: Session | None = None,
    conflict_alias_ids: set[int] | None = None,
) -> PrintAgentRead:
    is_online, status_text = _agent_status(agent)
    last_seen_age_seconds = None
    if agent.last_seen_at:
        last_seen = agent.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        last_seen_age_seconds = max(0, int((datetime.now(timezone.utc) - last_seen).total_seconds()))
    queue_actions = sorted(
        agent.queue_actions,
        key=lambda action: (action.requested_at, action.id),
        reverse=True,
    )[:20] if include_jobs else []
    return PrintAgentRead(
        id=agent.id,
        agent_uid=agent.agent_uid,
        computer_name=agent.computer_name,
        os_user=agent.os_user,
        version=agent.version,
        ip_address=agent.ip_address,
        capture_mode=agent.capture_mode,
        event_log_enabled=agent.event_log_enabled,
        auto_update_enabled=agent.auto_update_enabled,
        local_admin=agent.local_admin,
        last_error=agent.last_error,
        last_seen_at=agent.last_seen_at,
        last_seen_age_seconds=last_seen_age_seconds,
        created_at=agent.created_at,
        is_online=is_online,
        status=status_text,
        health_alerts=_agent_health_alerts(agent, is_online, db, conflict_alias_ids),
        aliases=[_alias_to_read(agent, alias) for alias in agent.aliases],
        recent_jobs=_recent_jobs(db, agent) if include_jobs and db is not None else [],
        queue_actions=queue_actions,
        recent_logs=_recent_logs(db, agent) if include_jobs and db is not None else [],
    )


def _bind_successful_queue_action(db: Session, action: AgentQueueAction) -> None:
    if action.status != AgentQueueActionStatus.succeeded:
        return

    queue_name = action.queue_name.strip()
    normalized_queue_name = _normalize_alias_name(queue_name)
    if action.action_type in (AgentQueueActionType.create_queue, AgentQueueActionType.restore_queue):
        if not action.printer_id:
            return
        alias = (
            db.query(PrinterAlias)
            .filter(
                PrinterAlias.organization_id == action.organization_id,
                PrinterAlias.agent_id == action.agent_id,
                or_(
                    PrinterAlias.queue_name == queue_name,
                    PrinterAlias.normalized_queue_name == normalized_queue_name,
                ),
            )
            .first()
        )
        if not alias:
            alias = PrinterAlias(
                organization_id=action.organization_id,
                agent_id=action.agent_id,
                queue_name=queue_name,
            )
            db.add(alias)
            db.flush()
        alias.printer_id = action.printer_id
        alias.normalized_queue_name = normalized_queue_name
        alias.driver_name = _clean_optional(action.driver_name) or alias.driver_name
        alias.port_name = _clean_optional(action.port_name) or alias.port_name
        alias.ip_address = _clean_optional(action.ip_address) or alias.ip_address
        alias.connection_type = alias.connection_type or ("network" if action.ip_address else None)
        alias.last_seen_at = datetime.now(timezone.utc)
        return

    if action.action_type == AgentQueueActionType.remove_queue:
        alias = (
            db.query(PrinterAlias)
            .filter(
                PrinterAlias.organization_id == action.organization_id,
                PrinterAlias.agent_id == action.agent_id,
                or_(
                    PrinterAlias.queue_name == queue_name,
                    PrinterAlias.normalized_queue_name == normalized_queue_name,
                ),
            )
            .first()
        )
        if alias:
            alias.printer_id = None


def _find_bound_printer_alias(
    db: Session,
    organization_id: int,
    *,
    serial_number: str | None = None,
    ip_address: str | None = None,
    device_id: str | None = None,
    fingerprint: str | None = None,
) -> PrinterAlias | None:
    filters = [
        (PrinterAlias.serial_number, serial_number),
        (PrinterAlias.ip_address, ip_address),
        (PrinterAlias.device_id, device_id),
        (PrinterAlias.fingerprint, fingerprint),
    ]
    for column, value in filters:
        alias = _find_alias_by_identity(db, organization_id, column, value, require_printer=True)
        if alias:
            return alias
    return None


def _find_printer_for_queue_metadata(db: Session, organization_id: int, queue: AgentQueuePayload) -> Printer | None:
    serial_number = _clean_optional(queue.serial_number)
    ip_address = _clean_optional(queue.ip_address)
    if serial_number:
        printer = _find_printer_by_serial(db, organization_id, serial_number)
        if printer:
            if ip_address:
                printer.ip_address = ip_address
            return printer

    if ip_address:
        printer = db.query(Printer).filter(Printer.organization_id == organization_id, Printer.ip_address == ip_address).first()
        if printer:
            if serial_number and not printer.serial_number:
                printer.serial_number = serial_number
            return printer

    alias = _find_bound_printer_alias(
        db,
        organization_id,
        serial_number=serial_number,
        ip_address=ip_address,
        device_id=queue.device_id,
        fingerprint=queue.fingerprint,
    )
    if alias and alias.printer:
        if serial_number and not alias.printer.serial_number:
            alias.printer.serial_number = serial_number
        if ip_address and (not alias.printer.ip_address or _same_identity(alias.printer.serial_number, serial_number)):
            alias.printer.ip_address = ip_address
        return alias.printer
    return None


def _validate_queue_action_payload(
    db: Session,
    payload: AgentQueueActionCreate,
    organization_id: int,
    *,
    require_printer_for_create: bool = False,
) -> Printer | None:
    printer = None
    if payload.printer_id is not None:
        printer = db.query(Printer).filter(Printer.organization_id == organization_id, Printer.id == payload.printer_id).first()
        if not printer:
            raise HTTPException(status_code=404, detail="Impressora nao encontrada")
        if (
            payload.action_type in (AgentQueueActionType.create_queue, AgentQueueActionType.restore_queue)
            and not printer.is_active
        ):
            raise HTTPException(status_code=409, detail="Impressora inativa nao pode receber criacao ou restauracao de fila")
    elif require_printer_for_create and payload.action_type in (AgentQueueActionType.create_queue, AgentQueueActionType.restore_queue):
        raise HTTPException(status_code=422, detail="Impressora fisica obrigatoria para criar ou restaurar fila em lote")

    if payload.action_type in (AgentQueueActionType.create_queue, AgentQueueActionType.restore_queue):
        if not _clean_optional(payload.driver_name):
            raise HTTPException(status_code=422, detail="Driver obrigatorio para criar fila")
        if not _clean_optional(payload.port_name) and not _clean_optional(payload.ip_address):
            raise HTTPException(status_code=422, detail="Informe IP ou porta para criar fila")
    return printer


def _new_queue_action(
    *,
    organization_id: int,
    agent_id: int,
    printer_id: int | None,
    requested_by_user_id: int,
    payload: AgentQueueActionCreate,
) -> AgentQueueAction:
    return AgentQueueAction(
        organization_id=organization_id,
        agent_id=agent_id,
        printer_id=printer_id,
        requested_by_user_id=requested_by_user_id,
        action_type=payload.action_type,
        queue_name=payload.queue_name.strip(),
        driver_name=_clean_optional(payload.driver_name),
        port_name=_clean_optional(payload.port_name),
        ip_address=_clean_optional(payload.ip_address),
        status=AgentQueueActionStatus.pending,
    )


def _active_queue_action_conflicts(
    db: Session,
    organization_id: int,
    agent_ids: list[int],
    queue_name: str,
) -> list[AgentQueueAction]:
    normalized_queue_name = _normalize_alias_name(queue_name)
    if not agent_ids or not normalized_queue_name:
        return []
    active_actions = (
        db.query(AgentQueueAction)
        .filter(
            AgentQueueAction.organization_id == organization_id,
            AgentQueueAction.agent_id.in_(agent_ids),
            AgentQueueAction.status.in_(ACTIVE_QUEUE_ACTION_STATUSES),
        )
        .all()
    )
    return [
        action
        for action in active_actions
        if _normalize_alias_name(action.queue_name) == normalized_queue_name
    ]


def _ensure_no_active_queue_action(
    db: Session,
    organization_id: int,
    agents: list[PrintAgent],
    queue_name: str,
) -> None:
    conflicts = _active_queue_action_conflicts(db, organization_id, [agent.id for agent in agents], queue_name)
    if not conflicts:
        return
    samples = []
    for action in conflicts[:3]:
        agent_name = action.agent.computer_name if action.agent else f"agent {action.agent_id}"
        samples.append(f"{agent_name}: {action.queue_name} ({action.action_type.value})")
    suffix = f": {', '.join(samples)}" if samples else ""
    raise HTTPException(
        status_code=409,
        detail=f"Ja existe acao remota pendente ou em execucao para esta fila{suffix}",
    )


def _queue_action_audit_metadata(action: AgentQueueAction, agent: PrintAgent | None = None, *, bulk: bool | None = None) -> dict:
    metadata = {
        "agent_id": action.agent_id,
        "agent_uid": agent.agent_uid if agent else None,
        "computer_name": agent.computer_name if agent else None,
        "printer_id": action.printer_id,
        "action_type": action.action_type.value,
        "queue_name": action.queue_name,
        "driver_name": action.driver_name,
        "port_name": action.port_name,
        "ip_address": action.ip_address,
    }
    if bulk is not None:
        metadata["bulk"] = bulk
    return metadata


def _deployment_organization_read(db: Session, organization: Organization) -> AgentDeploymentOrganizationRead:
    agent_user = (
        db.query(User)
        .filter(
            User.organization_id == organization.id,
            User.role == UserRole.agent,
            User.is_active.is_(True),
        )
        .order_by(User.id)
        .first()
    )
    return AgentDeploymentOrganizationRead(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        is_active=organization.is_active,
        billing_status=organization.billing_status,
        agent_username=agent_user.username if agent_user else None,
    )


@router.get("/version", response_model=AgentVersionRead)
def agent_version(
    current_version: str | None = Query(default=None),
    _: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> AgentVersionRead:
    latest = _latest_agent_release_file()
    file_exists = latest is not None
    published_version = latest[0].version if latest else settings.agent_latest_version
    return AgentVersionRead(
        latest_version=published_version,
        update_available=file_exists and is_newer_version(published_version, current_version),
        mandatory=False,
        download_url="/agent/download" if file_exists else None,
        sha256=latest[1].sha256 if latest else None,
    )


@router.get("/download")
def download_agent_update(_: User = Depends(require_roles(UserRole.agent, UserRole.admin))) -> FileResponse:
    latest = _latest_agent_release_file()
    if not latest:
        raise HTTPException(status_code=404, detail="Atualizacao do agent nao publicada")
    path = _release_file(latest[0].version, latest[1].filename)
    if _publishable_file_size(path) is None:
        raise HTTPException(status_code=404, detail="Atualizacao do agent nao publicada")
    if _sha256(path) != latest[1].sha256:
        raise HTTPException(status_code=409, detail="Checksum da atualizacao publicada diverge do manifest")
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=path.name,
    )


@router.get("/releases", response_model=list[AgentReleaseRead])
def list_agent_releases(_: User = Depends(require_roles(UserRole.admin, UserRole.manager))) -> list[AgentReleaseRead]:
    return _load_release_manifest()


@router.get("/deployment-organizations", response_model=list[AgentDeploymentOrganizationRead])
def list_agent_deployment_organizations(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> list[AgentDeploymentOrganizationRead]:
    if _can_manage_all_organizations(actor):
        organizations = (
            db.query(Organization)
            .filter(Organization.is_active.is_(True), Organization.billing_status != "suspended")
            .order_by(Organization.name)
            .all()
        )
        return [_deployment_organization_read(db, organization) for organization in organizations]
    return [_deployment_organization_read(db, actor.organization)] if organization_allows_access(actor.organization) else []


@router.get("/releases/{version}/download")
def download_agent_release_file(
    version: str,
    filename: str = Query(min_length=1, max_length=180),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> FileResponse:
    if not _is_safe_release_filename(filename):
        raise HTTPException(status_code=400, detail="Nome de arquivo invalido")
    release = _release_or_404(version)
    file_entry = next((file for file in release.files if file.filename == filename), None)
    if not file_entry:
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    path = _release_file(version, filename)
    if _publishable_file_size(path) is None:
        raise HTTPException(status_code=404, detail="Arquivo nao publicado")
    if _sha256(path) != file_entry.sha256:
        raise HTTPException(status_code=409, detail="Checksum do arquivo publicado diverge do manifest")
    write_audit(
        db,
        action="agent_release_downloaded",
        entity="agent_releases",
        entity_id=None,
        actor_user_id=actor.id,
        metadata={
            "version": version,
            "filename": filename,
            "kind": file_entry.kind,
            "sha256": file_entry.sha256,
        },
        organization_id=actor.organization_id,
    )
    db.commit()
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=filename,
    )


@router.get("/releases/{version}/checksums")
def download_agent_release_checksums(
    version: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Response:
    release = _release_or_404(version)
    content = _release_checksums_text(release)
    filename = f"SHA256SUMS-{version}.txt"
    write_audit(
        db,
        action="agent_release_checksums_downloaded",
        entity="agent_releases",
        entity_id=None,
        actor_user_id=actor.id,
        metadata={
            "version": release.version,
            "filename": filename,
            "file_count": len(release.files),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        },
        organization_id=actor.organization_id,
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/heartbeat", response_model=PrintAgentRead)
def agent_heartbeat(
    payload: AgentHeartbeatPayload,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> PrintAgentRead:
    now = datetime.now(timezone.utc)
    agent_uid = _clean_optional(payload.agent_uid)
    if not agent_uid:
        raise HTTPException(status_code=422, detail="agent_uid obrigatorio")

    agent = (
        db.query(PrintAgent)
        .options(selectinload(PrintAgent.aliases))
        .filter(PrintAgent.organization_id == actor.organization_id, PrintAgent.agent_uid == agent_uid)
        .first()
    )
    if not agent:
        agent = PrintAgent(organization_id=actor.organization_id, agent_uid=agent_uid)
        db.add(agent)
        db.flush()

    agent.computer_name = _clean_optional(payload.computer_name)
    agent.os_user = _clean_optional(payload.os_user)
    agent.version = _clean_optional(payload.version)
    agent.ip_address = _client_ip(request)
    agent.capture_mode = _clean_optional(payload.capture_mode)
    agent.event_log_enabled = payload.event_log_enabled
    agent.auto_update_enabled = payload.auto_update_enabled
    agent.local_admin = payload.local_admin
    agent.last_error = _clean_optional(payload.last_error)
    agent.last_seen_at = now

    existing_aliases = {
        alias.queue_name: alias
        for alias in db.query(PrinterAlias)
        .filter(PrinterAlias.organization_id == actor.organization_id, PrinterAlias.agent_id == agent.id)
        .all()
    }
    existing_aliases_by_normalized = {
        normalized: alias
        for alias in existing_aliases.values()
        if (normalized := alias.normalized_queue_name or _normalize_alias_name(alias.queue_name))
    }
    for queue in payload.queues:
        queue_name = queue.queue_name.strip()
        normalized_queue_name = _normalize_alias_name(queue_name)
        alias = existing_aliases.get(queue_name) or (existing_aliases_by_normalized.get(normalized_queue_name) if normalized_queue_name else None)
        if not alias:
            alias = PrinterAlias(
                organization_id=actor.organization_id,
                agent_id=agent.id,
                queue_name=queue_name,
            )
            db.add(alias)
            db.flush()
            existing_aliases[queue_name] = alias
        elif alias.queue_name != queue_name:
            alias.queue_name = queue_name
            existing_aliases[queue_name] = alias
        if normalized_queue_name:
            existing_aliases_by_normalized[normalized_queue_name] = alias
        alias.normalized_queue_name = normalized_queue_name
        alias.computer_name = agent.computer_name
        alias.driver_name = _clean_optional(queue.driver_name)
        alias.port_name = _clean_optional(queue.port_name)
        alias.connection_type = _clean_optional(queue.connection_type)
        alias.ip_address = _clean_optional(queue.ip_address)
        alias.serial_number = _clean_optional(queue.serial_number)
        alias.device_id = _clean_optional(queue.device_id)
        alias.fingerprint = _clean_optional(queue.fingerprint)
        alias.last_seen_at = now
        if alias.printer_id is None:
            printer = _find_printer_for_queue_metadata(db, actor.organization_id, queue)
            if printer:
                alias.printer_id = printer.id

    _store_agent_logs(db, agent, payload, now)
    db.commit()
    agent = (
        db.query(PrintAgent)
        .options(selectinload(PrintAgent.aliases))
        .filter(PrintAgent.id == agent.id, PrintAgent.organization_id == actor.organization_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent nao encontrado")
    return _agent_to_read(agent, db=db)


@router.get("/agents", response_model=list[PrintAgentRead])
def list_agents(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[PrintAgentRead]:
    agents = (
        db.query(PrintAgent)
        .options(selectinload(PrintAgent.aliases), selectinload(PrintAgent.queue_actions))
        .filter(PrintAgent.organization_id == actor.organization_id)
        .order_by(PrintAgent.last_seen_at.desc().nullslast(), PrintAgent.computer_name, PrintAgent.id)
        .all()
    )
    conflict_ids = conflicting_alias_ids(db, actor.organization_id)
    return [_agent_to_read(agent, db=db, conflict_alias_ids=conflict_ids) for agent in agents]


@router.get("/agents/{agent_id}", response_model=PrintAgentRead)
def get_agent_detail(
    agent_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> PrintAgentRead:
    agent = (
        db.query(PrintAgent)
        .options(
            selectinload(PrintAgent.aliases),
            selectinload(PrintAgent.aliases).selectinload(PrinterAlias.printer),
            selectinload(PrintAgent.queue_actions),
        )
        .filter(PrintAgent.organization_id == actor.organization_id, PrintAgent.id == agent_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent nao encontrado")
    conflict_ids = conflicting_alias_ids(db, actor.organization_id)
    return _agent_to_read(agent, include_jobs=True, db=db, conflict_alias_ids=conflict_ids)


@router.post("/agents/{agent_id}/queue-actions", response_model=AgentQueueActionRead)
def create_queue_action(
    agent_id: int,
    payload: AgentQueueActionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> AgentQueueAction:
    agent = db.query(PrintAgent).filter(PrintAgent.organization_id == actor.organization_id, PrintAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent nao encontrado")

    printer = _validate_queue_action_payload(db, payload, actor.organization_id)
    _ensure_no_active_queue_action(db, actor.organization_id, [agent], payload.queue_name)
    action = _new_queue_action(
        organization_id=actor.organization_id,
        agent_id=agent.id,
        printer_id=printer.id if printer else None,
        requested_by_user_id=actor.id,
        payload=payload,
    )
    db.add(action)
    db.flush()
    write_audit(
        db,
        action="agent_queue_action_created",
        entity="agent_queue_actions",
        entity_id=action.id,
        actor_user_id=actor.id,
        metadata=_queue_action_audit_metadata(action, agent, bulk=False),
        organization_id=actor.organization_id,
    )
    db.commit()
    db.refresh(action)
    return action


@router.post("/queue-actions/bulk", response_model=list[AgentQueueActionRead])
def create_bulk_queue_actions(
    payload: AgentQueueBulkActionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> list[AgentQueueAction]:
    printer = _validate_queue_action_payload(db, payload, actor.organization_id, require_printer_for_create=True)

    agents_query = db.query(PrintAgent).filter(PrintAgent.organization_id == actor.organization_id)
    if payload.apply_to_all:
        agents = agents_query.order_by(PrintAgent.computer_name, PrintAgent.id).all()
    else:
        agents = agents_query.filter(PrintAgent.id.in_(payload.agent_ids)).order_by(PrintAgent.computer_name, PrintAgent.id).all()
        found_ids = {agent.id for agent in agents}
        missing_ids = sorted(set(payload.agent_ids) - found_ids)
        if missing_ids:
            raise HTTPException(status_code=404, detail=f"Agent(s) nao encontrado(s): {missing_ids}")

    if not agents:
        raise HTTPException(status_code=404, detail="Nenhum agent encontrado para aplicar a fila")

    _ensure_no_active_queue_action(db, actor.organization_id, agents, payload.queue_name)
    actions = [
        _new_queue_action(
            organization_id=actor.organization_id,
            agent_id=agent.id,
            printer_id=printer.id if printer else None,
            requested_by_user_id=actor.id,
            payload=payload,
        )
        for agent in agents
    ]
    db.add_all(actions)
    db.flush()
    for action in actions:
        write_audit(
            db,
            action="agent_queue_action_created",
            entity="agent_queue_actions",
            entity_id=action.id,
            actor_user_id=actor.id,
            metadata=_queue_action_audit_metadata(action, action.agent, bulk=True),
            organization_id=actor.organization_id,
        )
    db.commit()
    for action in actions:
        db.refresh(action)
    return actions


@router.get("/queue-actions", response_model=list[AgentQueueActionRead])
def poll_queue_actions(
    agent_uid: str = Query(min_length=1, max_length=120),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> list[AgentQueueAction]:
    agent = db.query(PrintAgent).filter(PrintAgent.organization_id == actor.organization_id, PrintAgent.agent_uid == agent_uid).first()
    if not agent:
        return []

    now = datetime.now(timezone.utc)
    stale_cutoff = now - QUEUE_ACTION_STALE_AFTER
    actions = (
        db.query(AgentQueueAction)
        .filter(
            AgentQueueAction.organization_id == actor.organization_id,
            AgentQueueAction.agent_id == agent.id,
            or_(
                AgentQueueAction.status == AgentQueueActionStatus.pending,
                and_(
                    AgentQueueAction.status == AgentQueueActionStatus.running,
                    or_(
                        AgentQueueAction.dispatched_at.is_(None),
                        AgentQueueAction.dispatched_at < stale_cutoff,
                    ),
                ),
            ),
        )
        .order_by(AgentQueueAction.requested_at, AgentQueueAction.id)
        .limit(10)
        .all()
    )
    for action in actions:
        previous_status = action.status.value if hasattr(action.status, "value") else str(action.status)
        previous_dispatched_at = action.dispatched_at
        is_redispatch = action.status == AgentQueueActionStatus.running
        action.status = AgentQueueActionStatus.running
        action.dispatched_at = now
        write_audit(
            db,
            action="agent_queue_action_dispatched",
            entity="agent_queue_actions",
            entity_id=action.id,
            actor_user_id=actor.id,
            metadata={
                "agent_id": agent.id,
                "agent_uid": agent.agent_uid,
                "action_type": action.action_type.value,
                "queue_name": action.queue_name,
                "redispatch": is_redispatch,
                "previous_status": previous_status,
                "previous_dispatched_at": previous_dispatched_at.isoformat() if previous_dispatched_at else None,
            },
            organization_id=actor.organization_id,
        )
    db.commit()
    for action in actions:
        db.refresh(action)
    return actions


@router.post("/queue-actions/{action_id}/cancel", response_model=AgentQueueActionRead)
def cancel_queue_action(
    action_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> AgentQueueAction:
    action = (
        db.query(AgentQueueAction)
        .join(PrintAgent, PrintAgent.id == AgentQueueAction.agent_id)
        .filter(
            AgentQueueAction.organization_id == actor.organization_id,
            AgentQueueAction.id == action_id,
        )
        .first()
    )
    if not action:
        raise HTTPException(status_code=404, detail="Acao nao encontrada")
    if action.status not in (AgentQueueActionStatus.pending, AgentQueueActionStatus.running):
        raise HTTPException(status_code=409, detail="Apenas acoes pendentes ou em execucao podem ser canceladas")

    previous_status = action.status.value
    action.status = AgentQueueActionStatus.failed
    action.result_message = "Cancelada pelo administrador antes da confirmacao do agent"
    action.completed_at = datetime.now(timezone.utc)
    write_audit(
        db,
        action="agent_queue_action_cancelled",
        entity="agent_queue_actions",
        entity_id=action.id,
        actor_user_id=actor.id,
        metadata={
            **_queue_action_audit_metadata(action, action.agent),
            "previous_status": previous_status,
            "status": action.status.value,
            "result_message": action.result_message,
        },
        organization_id=actor.organization_id,
    )
    db.commit()
    db.refresh(action)
    return action


@router.post("/queue-actions/{action_id}/result", response_model=AgentQueueActionRead)
def finish_queue_action(
    action_id: int,
    payload: AgentQueueActionResult,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> AgentQueueAction:
    if payload.status not in (AgentQueueActionStatus.succeeded, AgentQueueActionStatus.failed):
        raise HTTPException(status_code=422, detail="Resultado deve ser succeeded ou failed")

    action = (
        db.query(AgentQueueAction)
        .join(PrintAgent, PrintAgent.id == AgentQueueAction.agent_id)
        .filter(
            AgentQueueAction.organization_id == actor.organization_id,
            AgentQueueAction.id == action_id,
        )
        .first()
    )
    if not action:
        raise HTTPException(status_code=404, detail="Acao nao encontrada")
    if action.status != AgentQueueActionStatus.running:
        raise HTTPException(status_code=409, detail="Acao remota nao esta em execucao")
    if actor.role == UserRole.agent:
        if not payload.agent_uid:
            raise HTTPException(status_code=403, detail="agent_uid obrigatorio para confirmar acao remota")
        if not action.agent or action.agent.agent_uid != payload.agent_uid:
            raise HTTPException(status_code=403, detail="Agent nao autorizado para confirmar esta acao")

    action.status = payload.status
    action.result_message = _clean_optional(payload.result_message)
    action.completed_at = datetime.now(timezone.utc)
    _bind_successful_queue_action(db, action)
    write_audit(
        db,
        action="agent_queue_action_finished",
        entity="agent_queue_actions",
        entity_id=action.id,
        actor_user_id=actor.id,
        metadata={
            **_queue_action_audit_metadata(action, action.agent),
            "status": action.status.value,
            "result_message": action.result_message,
        },
        organization_id=actor.organization_id,
    )
    db.commit()
    db.refresh(action)
    return action
