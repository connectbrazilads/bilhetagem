import logging
import threading
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.organization import Organization
from app.services.audit_service import write_audit
from app.services.email_service import send_due_monthly_report_email

logger = logging.getLogger("printbilling.email_scheduler")

_scheduler_started = False
_scheduler_lock = threading.Lock()


def send_due_monthly_reports_once(db: Session, now: datetime | None = None) -> list[dict]:
    organizations = (
        db.query(Organization)
        .filter(Organization.is_active.is_(True), Organization.billing_status != "suspended")
        .order_by(Organization.id)
        .all()
    )
    results: list[dict] = []
    for organization in organizations:
        try:
            result = send_due_monthly_report_email(db, organization.id, now=now)
            entry = {"organization_id": organization.id, "organization_slug": organization.slug, **result}
            if result.get("sent"):
                write_audit(
                    db,
                    action="monthly_closing_due_email_sent",
                    entity="monthly_closings",
                    entity_id=result.get("closing_id"),
                    organization_id=organization.id,
                    metadata={
                        "period": result.get("period"),
                        "recipients": result.get("recipients", []),
                        "attachments": result.get("attachments", []),
                        "automatic": True,
                    },
                )
                db.commit()
            results.append(entry)
        except Exception as exc:
            db.rollback()
            logger.exception("Falha no envio mensal automatico da empresa %s", organization.slug)
            results.append(
                {
                    "organization_id": organization.id,
                    "organization_slug": organization.slug,
                    "sent": False,
                    "reason": str(exc),
                    "error": True,
                }
            )
    return results


def _scheduler_loop(interval_seconds: int) -> None:
    while True:
        db = SessionLocal()
        try:
            send_due_monthly_reports_once(db)
        finally:
            db.close()
        threading.Event().wait(interval_seconds)


def start_monthly_report_email_scheduler() -> bool:
    global _scheduler_started
    if not settings.monthly_report_email_scheduler_enabled:
        return False

    with _scheduler_lock:
        if _scheduler_started:
            return False
        interval = max(int(settings.monthly_report_email_scheduler_interval_seconds), 300)
        thread = threading.Thread(
            target=_scheduler_loop,
            args=(interval,),
            name="monthly-report-email-scheduler",
            daemon=True,
        )
        thread.start()
        _scheduler_started = True
        logger.info("Monthly report email scheduler started with interval %ss", interval)
        return True
