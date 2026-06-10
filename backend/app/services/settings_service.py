from typing import Any
from sqlalchemy.orm import Session
from app.models.print_job import JobStatus, PrintJob
from app.models.system_setting import SystemSetting
from app.core.config import settings
from app.services.organization_service import get_or_create_default_organization
from app.services.quota_service import get_or_create_current_quota


def _resolve_organization_id(db: Session, organization_id: int | None) -> int:
    return organization_id or get_or_create_default_organization(db).id


def get_system_settings_dict(db: Session, organization_id: int | None = None) -> dict[str, Any]:
    organization_id = _resolve_organization_id(db, organization_id)
    # Query all settings from the database
    db_settings = db.query(SystemSetting).filter(SystemSetting.organization_id == organization_id).all()
    settings_dict = {s.key: s.value for s in db_settings}

    def parse_bool(val: str | None, default: bool) -> bool:
        if val is None:
            return default
        return val.lower() in ("true", "1", "yes")

    return {
        "default_monthly_quota": int(settings_dict.get("default_monthly_quota", str(settings.default_monthly_quota))),
        "auto_create_users": parse_bool(settings_dict.get("auto_create_users", None), settings.auto_create_users),
        "blocking_enabled": parse_bool(settings_dict.get("blocking_enabled", None), True),
        "show_balance": parse_bool(settings_dict.get("show_balance", None), True),
        "safe_release_enabled": parse_bool(settings_dict.get("safe_release_enabled", None), settings.safe_release_enabled),
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
