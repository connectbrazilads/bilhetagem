from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate, PrintJobDecision
from app.services.audit_service import write_audit
from app.services.quota_service import can_consume, get_or_create_current_quota


def _resolve_user(db: Session, username: str, auto_create_users: bool) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    if not auto_create_users:
        raise ValueError(f"Usuário '{username}' não cadastrado")
    user = User(username=username, full_name=username, role=UserRole.user, is_active=True)
    db.add(user)
    db.flush()
    return user


def _resolve_printer(db: Session, printer_name: str, is_color: bool) -> Printer:
    printer = db.query(Printer).filter(Printer.name == printer_name).first()
    if printer:
        return printer
    if not settings.auto_create_printers:
        raise ValueError(f"Impressora '{printer_name}' não cadastrada")
    printer = Printer(name=printer_name, is_color=is_color)
    db.add(printer)
    db.flush()
    return printer


def register_print_job(db: Session, payload: PrintJobCreate) -> PrintJobDecision:
    from app.services.settings_service import get_system_settings_dict
    sys_settings = get_system_settings_dict(db)

    user = _resolve_user(db, payload.username, sys_settings["auto_create_users"])
    printer = _resolve_printer(db, payload.printer_name, payload.is_color)
    quota = get_or_create_current_quota(db, user, payload.submitted_at)

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
            reason = "Cota de páginas insuficiente (fila de liberação inclusa)"
        else:
            reason = "Saldo mensal insuficiente (fila de liberação inclusa)"
    else:
        if sys_settings["safe_release_enabled"]:
            status = JobStatus.pending_release
        else:
            status = JobStatus.authorized
            quota.used_pages += payload.pages
            quota.used_balance += cost

    job = PrintJob(
        user_id=user.id,
        printer_id=printer.id,
        external_job_id=payload.external_job_id,
        document_name=payload.document_name,
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
