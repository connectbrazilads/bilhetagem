from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.print_agent import PrintAgent
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate, PrintJobDecision
from app.services.audit_service import write_audit
from app.services.quota_service import can_consume, get_or_create_current_quota


def _resolve_user(db: Session, username: str, auto_create_users: bool) -> User:
    username = _normalize_username(username)
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    if not auto_create_users:
        raise ValueError(f"Usuario '{username}' nao cadastrado")
    user = User(username=username, full_name=username, role=UserRole.user, is_active=True)
    db.add(user)
    db.flush()
    return user


def _normalize_username(username: str) -> str:
    normalized = username.strip()
    if "\\" in normalized:
        normalized = normalized.rsplit("\\", 1)[-1]
    if "@" in normalized:
        normalized = normalized.split("@", 1)[0]
    return normalized.strip().lower() or "unknown"


def _resolve_printer(db: Session, printer_name: str, is_color: bool) -> Printer:
    printer = db.query(Printer).filter(Printer.name == printer_name).first()
    if printer:
        return printer
    if not settings.auto_create_printers:
        raise ValueError(f"Impressora '{printer_name}' nao cadastrada")
    printer = Printer(name=printer_name, is_color=is_color)
    db.add(printer)
    db.flush()
    return printer


def _normalize_alias_name(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.strip().lower().split()) or None


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _upsert_agent(db: Session, payload: PrintJobCreate) -> PrintAgent | None:
    agent_uid = _clean_optional(payload.agent_uid)
    if not agent_uid:
        return None
    from datetime import datetime, timezone

    agent = db.query(PrintAgent).filter(PrintAgent.agent_uid == agent_uid).first()
    if not agent:
        agent = PrintAgent(agent_uid=agent_uid)
        db.add(agent)
        db.flush()
    agent.computer_name = _clean_optional(payload.computer_name)
    agent.last_seen_at = datetime.now(timezone.utc)
    return agent


def _find_existing_printer(db: Session, payload: PrintJobCreate, agent: PrintAgent | None) -> Printer | None:
    serial = _clean_optional(payload.printer_serial)
    if serial:
        printer = db.query(Printer).filter(Printer.serial_number == serial).first()
        if printer:
            return printer

    ip_address = _clean_optional(payload.printer_ip_address)
    if ip_address:
        printer = db.query(Printer).filter(Printer.ip_address == ip_address).first()
        if printer:
            return printer

    queue_name = _clean_optional(payload.queue_name) or payload.printer_name
    if agent and queue_name:
        alias = (
            db.query(PrinterAlias)
            .filter(PrinterAlias.agent_id == agent.id, PrinterAlias.queue_name == queue_name)
            .first()
        )
        if alias and alias.printer:
            return alias.printer

    fingerprint = _clean_optional(payload.printer_fingerprint)
    if fingerprint:
        alias = (
            db.query(PrinterAlias)
            .filter(PrinterAlias.fingerprint == fingerprint, PrinterAlias.printer_id.isnot(None))
            .first()
        )
        if alias and alias.printer:
            return alias.printer

    return db.query(Printer).filter(Printer.name == payload.printer_name).first()


def _resolve_printer_for_job(db: Session, payload: PrintJobCreate, agent: PrintAgent | None) -> Printer:
    printer = _find_existing_printer(db, payload, agent)
    if printer:
        if payload.printer_serial and not printer.serial_number:
            printer.serial_number = payload.printer_serial
        if payload.printer_ip_address and not printer.ip_address:
            printer.ip_address = payload.printer_ip_address
        return printer
    return _resolve_printer(db, payload.printer_name, payload.is_color)


def _upsert_printer_alias(db: Session, payload: PrintJobCreate, agent: PrintAgent | None, printer: Printer) -> PrinterAlias | None:
    queue_name = _clean_optional(payload.queue_name) or payload.printer_name
    if not queue_name:
        return None
    from datetime import datetime, timezone

    alias = None
    if agent:
        alias = (
            db.query(PrinterAlias)
            .filter(PrinterAlias.agent_id == agent.id, PrinterAlias.queue_name == queue_name)
            .first()
        )
    if alias is None and not agent and payload.printer_fingerprint:
        alias = (
            db.query(PrinterAlias)
            .filter(PrinterAlias.fingerprint == payload.printer_fingerprint)
            .first()
        )
    if alias is None:
        alias = PrinterAlias(agent_id=agent.id if agent else None, queue_name=queue_name)
        db.add(alias)
        db.flush()

    alias.printer_id = printer.id
    alias.normalized_queue_name = _normalize_alias_name(queue_name)
    alias.computer_name = _clean_optional(payload.computer_name)
    alias.driver_name = _clean_optional(payload.printer_driver_name)
    alias.port_name = _clean_optional(payload.printer_port_name)
    alias.connection_type = _clean_optional(payload.printer_connection_type)
    alias.ip_address = _clean_optional(payload.printer_ip_address)
    alias.serial_number = _clean_optional(payload.printer_serial)
    alias.device_id = _clean_optional(payload.printer_device_id)
    alias.fingerprint = _clean_optional(payload.printer_fingerprint)
    alias.last_seen_at = datetime.now(timezone.utc)
    return alias


def register_print_job(db: Session, payload: PrintJobCreate) -> PrintJobDecision:
    from app.services.settings_service import get_system_settings_dict
    sys_settings = get_system_settings_dict(db)

    user = _resolve_user(db, payload.username, sys_settings["auto_create_users"])
    agent = _upsert_agent(db, payload)
    printer = _resolve_printer_for_job(db, payload, agent)
    alias = _upsert_printer_alias(db, payload, agent, printer)
    quota = get_or_create_current_quota(db, user, payload.submitted_at)
    is_print_event_log_job = bool(payload.external_job_id and payload.external_job_id.startswith("eventlog:"))

    if payload.external_job_id:
        existing_job = (
            db.query(PrintJob)
            .filter(
                PrintJob.printer_id == printer.id,
                PrintJob.external_job_id == payload.external_job_id,
            )
            .order_by(PrintJob.id.desc())
            .first()
        )
        if existing_job:
            return PrintJobDecision(
                job_id=existing_job.id,
                status=existing_job.status,
                authorized=existing_job.status in (JobStatus.authorized, JobStatus.pending_release, JobStatus.released),
                remaining_pages=quota.remaining_pages,
                remaining_balance=quota.remaining_balance,
                reason=existing_job.reason,
            )

    # Calculate print job cost
    cost = payload.pages * (printer.cost_color if payload.is_color else printer.cost_mono)

    # Calculate total cost/pages of currently pending release jobs for this user to prevent double-spending
    import sqlalchemy as sa
    pending_cost = db.query(sa.func.sum(PrintJob.cost)).filter(
        PrintJob.user_id == user.id,
        PrintJob.status == JobStatus.pending_release
    ).scalar() or 0.0
    pending_pages = db.query(sa.func.sum(PrintJob.pages)).filter(
        PrintJob.user_id == user.id,
        PrintJob.status == JobStatus.pending_release
    ).scalar() or 0

    # Validate against effective pages and balance (subtracting pending ones)
    effective_remaining_pages = quota.remaining_pages - pending_pages
    effective_remaining_balance = quota.remaining_balance - pending_cost

    authorized_pages = effective_remaining_pages >= payload.pages
    authorized_balance = effective_remaining_balance >= cost

    if sys_settings["blocking_enabled"]:
        authorized = authorized_pages and authorized_balance
    else:
        authorized = True

    reason = None
    if not authorized:
        status = JobStatus.blocked
        if not authorized_pages:
            reason = "Cota de paginas insuficiente (fila de liberacao inclusa)"
        else:
            reason = "Saldo mensal insuficiente (fila de liberacao inclusa)"
    else:
        if sys_settings["safe_release_enabled"] and not is_print_event_log_job:
            status = JobStatus.pending_release
        else:
            status = JobStatus.authorized
            quota.used_pages += payload.pages
            quota.used_balance += cost

    job = PrintJob(
        user_id=user.id,
        printer_id=printer.id,
        printer_alias_id=alias.id if alias else None,
        agent_id=agent.id if agent else None,
        external_job_id=payload.external_job_id,
        document_name=payload.document_name,
        computer_name=payload.computer_name,
        queue_name=payload.queue_name or payload.printer_name,
        pages=payload.pages,
        is_color=payload.is_color,
        cost=cost,
        status=status,
        reason=reason,
        submitted_at=payload.submitted_at,
    )
    db.add(job)
    db.flush()
    write_audit(
        db,
        action="print_job_authorized" if authorized else "print_job_blocked",
        entity="print_jobs",
        entity_id=job.id,
        metadata={
            "username": user.username,
            "printer": printer.name,
            "pages": payload.pages,
            "remaining_pages": quota.remaining_pages,
            "cost": cost,
            "remaining_balance": quota.remaining_balance,
        },
    )
    db.commit()
    db.refresh(job)
    return PrintJobDecision(
        job_id=job.id,
        status=status,
        authorized=authorized,
        remaining_pages=quota.remaining_pages,
        remaining_balance=quota.remaining_balance,
        reason=reason,
    )
