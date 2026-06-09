from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.quota import Quota
from app.models.user import User


def get_or_create_current_quota(db: Session, user: User, moment: datetime | None = None) -> Quota:
    moment = moment or datetime.now(timezone.utc)
    quota = (
        db.query(Quota)
        .filter(Quota.user_id == user.id, Quota.year == moment.year, Quota.month == moment.month)
        .with_for_update()
        .first()
    )
    if quota:
        return quota

    latest_quota = db.query(Quota).filter(Quota.user_id == user.id).order_by(Quota.id.desc()).first()
    from app.services.settings_service import get_system_settings_dict
    sys_settings = get_system_settings_dict(db)
    monthly_limit = latest_quota.monthly_limit if latest_quota else sys_settings["default_monthly_quota"]
    monthly_balance = latest_quota.monthly_balance if latest_quota else 50.0
    quota = Quota(
        user_id=user.id,
        year=moment.year,
        month=moment.month,
        monthly_limit=monthly_limit,
        used_pages=0,
        monthly_balance=monthly_balance,
        used_balance=0.0
    )
    db.add(quota)
    db.flush()
    return quota


def can_consume(quota: Quota, pages: int) -> bool:
    return quota.remaining_pages >= pages
