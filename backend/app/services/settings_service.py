from typing import Any
from sqlalchemy.orm import Session
from app.models.print_job import JobStatus, PrintJob
from app.models.system_setting import SystemSetting
from app.core.config import settings
from app.services.organization_service import get_or_create_default_organization
from app.services.quota_service import get_or_create_current_quota
from app.services.audit_service import write_audit


MONTHLY_REPORT_EMAIL_DEFAULTS = {
    "enabled": False,
    "recipients": "",
    "day_of_month": 1,
    "include_pdf": True,
    "include_xlsx": True,
}


def _resolve_organization_id(db: Session, organization_id: int | None) -> int:
    return organization_id or get_or_create_default_organization(db).id


def _parse_bool(val: str | None, default: bool) -> bool:
    if val is None:
        return default
    normalized = val.strip().lower()
    if normalized in ("true", "1", "yes", "sim"):
        return True
    if normalized in ("false", "0", "no", "nao", "não"):
        return False
    return default


def _parse_int(val: str | None, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    if val is None:
        return default
    try:
        parsed = int(str(val).strip())
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed


def _parse_float(val: str | None, default: float, *, min_value: float | None = None) -> float:
    if val is None:
        return default
    try:
        parsed = float(str(val).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


def get_system_settings_dict(db: Session, organization_id: int | None = None) -> dict[str, Any]:
    organization_id = _resolve_organization_id(db, organization_id)
    # Query all settings from the database
    db_settings = db.query(SystemSetting).filter(SystemSetting.organization_id == organization_id).all()
    settings_dict = {s.key: s.value for s in db_settings}

    return {
        "default_monthly_quota": _parse_int(settings_dict.get("default_monthly_quota"), settings.default_monthly_quota, min_value=0),
        "default_printer_cost_mono": _parse_float(settings_dict.get("default_printer_cost_mono"), 0.05, min_value=0),
        "default_printer_cost_color": _parse_float(settings_dict.get("default_printer_cost_color"), 0.25, min_value=0),
        "auto_create_users": _parse_bool(settings_dict.get("auto_create_users", None), settings.auto_create_users),
        "blocking_enabled": _parse_bool(settings_dict.get("blocking_enabled", None), True),
        "show_balance": _parse_bool(settings_dict.get("show_balance", None), True),
        "safe_release_enabled": _parse_bool(settings_dict.get("safe_release_enabled", None), settings.safe_release_enabled),
        "web_print_enabled": _parse_bool(settings_dict.get("web_print_enabled", None), True),
    }


def update_system_settings(db: Session, updates: dict[str, Any], organization_id: int | None = None) -> dict[str, Any]:
    organization_id = _resolve_organization_id(db, organization_id)
    disabling_safe_release = updates.get("safe_release_enabled") is False
    for key, val in updates.items():
        # Store booleans as "true"/"false" and other values as string
        str_val = str(val).lower() if isinstance(val, bool) else str(val)
        setting = (
            db.query(SystemSetting)
            .filter(SystemSetting.organization_id == organization_id, SystemSetting.key == key)
            .first()
        )
        if not setting:
            setting = SystemSetting(organization_id=organization_id, key=key, value=str_val)
            db.add(setting)
        else:
            setting.value = str_val
    if disabling_safe_release:
        release_pending_jobs(db, organization_id)
    db.commit()
    return get_system_settings_dict(db, organization_id)


def get_monthly_report_email_settings(db: Session, organization_id: int | None = None) -> dict[str, Any]:
    organization_id = _resolve_organization_id(db, organization_id)
    rows = db.query(SystemSetting).filter(SystemSetting.organization_id == organization_id).all()
    settings_dict = {row.key: row.value for row in rows}
    prefix = "monthly_report_email_"
    return {
        "enabled": _parse_bool(settings_dict.get(f"{prefix}enabled"), MONTHLY_REPORT_EMAIL_DEFAULTS["enabled"]),
        "recipients": settings_dict.get(f"{prefix}recipients", MONTHLY_REPORT_EMAIL_DEFAULTS["recipients"]),
        "day_of_month": _parse_int(
            settings_dict.get(f"{prefix}day_of_month"),
            MONTHLY_REPORT_EMAIL_DEFAULTS["day_of_month"],
            min_value=1,
            max_value=28,
        ),
        "include_pdf": _parse_bool(settings_dict.get(f"{prefix}include_pdf"), MONTHLY_REPORT_EMAIL_DEFAULTS["include_pdf"]),
        "include_xlsx": _parse_bool(settings_dict.get(f"{prefix}include_xlsx"), MONTHLY_REPORT_EMAIL_DEFAULTS["include_xlsx"]),
    }


def update_monthly_report_email_settings(db: Session, updates: dict[str, Any], organization_id: int | None = None) -> dict[str, Any]:
    prefixed = {f"monthly_report_email_{key}": value for key, value in updates.items()}
    update_system_settings(db, prefixed, organization_id)
    return get_monthly_report_email_settings(db, organization_id)


def release_pending_jobs(db: Session, organization_id: int) -> None:
    pending_jobs = (
        db.query(PrintJob)
        .filter(PrintJob.organization_id == organization_id, PrintJob.status == JobStatus.pending_release)
        .all()
    )
    released_jobs = 0
    released_pages = 0
    released_cost = 0.0
    for job in pending_jobs:
        quota = get_or_create_current_quota(db, job.user, job.submitted_at)
        quota.used_pages += job.pages
        quota.used_balance += job.cost
        job.status = JobStatus.authorized
        job.reason = "Liberado automaticamente ao desativar Follow-Me"
        released_jobs += 1
        released_pages += job.pages
        released_cost += job.cost
    if released_jobs:
        write_audit(
            db,
            action="pending_jobs_auto_released",
            entity="print_jobs",
            organization_id=organization_id,
            metadata={
                "jobs": released_jobs,
                "pages": released_pages,
                "cost": round(released_cost, 2),
                "reason": "safe_release_disabled",
            },
        )
