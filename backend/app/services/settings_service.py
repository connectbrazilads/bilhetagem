from typing import Any
from sqlalchemy.orm import Session
from app.models.print_job import JobStatus, PrintJob
from app.models.system_setting import SystemSetting
from app.core.config import settings
from app.services.organization_service import get_or_create_default_organization
from app.services.quota_service import get_or_create_current_quota


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
    return val.lower() in ("true", "1", "yes")


def get_system_settings_dict(db: Session, organization_id: int | None = None) -> dict[str, Any]:
    organization_id = _resolve_organization_id(db, organization_id)
    # Query all settings from the database
    db_settings = db.query(SystemSetting).filter(SystemSetting.organization_id == organization_id).all()
    settings_dict = {s.key: s.value for s in db_settings}

    return {
        "default_monthly_quota": int(settings_dict.get("default_monthly_quota", str(settings.default_monthly_quota))),
        "default_printer_cost_mono": float(settings_dict.get("default_printer_cost_mono", "0.05")),
        "default_printer_cost_color": float(settings_dict.get("default_printer_cost_color", "0.25")),
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
        "day_of_month": int(settings_dict.get(f"{prefix}day_of_month", str(MONTHLY_REPORT_EMAIL_DEFAULTS["day_of_month"]))),
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
    for job in pending_jobs:
        quota = get_or_create_current_quota(db, job.user, job.submitted_at)
        quota.used_pages += job.pages
        quota.used_balance += job.cost
        job.status = JobStatus.authorized
        job.reason = "Liberado automaticamente ao desativar Follow-Me"
