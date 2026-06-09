from typing import Any
from sqlalchemy.orm import Session
from app.models.system_setting import SystemSetting
from app.core.config import settings


def get_system_settings_dict(db: Session) -> dict[str, Any]:
    # Query all settings from the database
    db_settings = db.query(SystemSetting).all()
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


def update_system_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    for key, val in updates.items():
        # Store booleans as "true"/"false" and other values as string
        str_val = str(val).lower() if isinstance(val, bool) else str(val)
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not setting:
            setting = SystemSetting(key=key, value=str_val)
            db.add(setting)
        else:
            setting.value = str_val
    db.commit()
    return get_system_settings_dict(db)
