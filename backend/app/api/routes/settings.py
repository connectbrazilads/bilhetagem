from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.user import User, UserRole
from app.schemas.settings import LDAPSettings, LDAPSettingsRead, GeneralSettings, MonthlyReportEmailSettings, OperationalSettings
from app.services.ldap_service import test_ldap_connection, sync_ldap_users
from app.services.settings_service import (
    get_ldap_settings,
    get_monthly_report_email_settings,
    get_system_settings_dict,
    update_ldap_settings,
    update_monthly_report_email_settings,
    update_system_settings,
)
from app.services.audit_service import write_audit

router = APIRouter(prefix="/settings", tags=["settings"])


def _changed_values(before: dict, after: dict) -> dict:
    changes = {}
    for key, after_value in after.items():
        before_value = before.get(key)
        if before_value != after_value:
            changes[key] = {"before": before_value, "after": after_value}
    return changes


@router.get("", response_model=GeneralSettings)
def get_general_settings(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.agent)),
) -> GeneralSettings:
    return GeneralSettings(**get_system_settings_dict(db, actor.organization_id))


@router.get("/operational", response_model=OperationalSettings)
def get_operational_settings(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> OperationalSettings:
    settings = get_system_settings_dict(db, actor.organization_id)
    return OperationalSettings(safe_release_enabled=settings["safe_release_enabled"])


@router.put("", response_model=GeneralSettings)
def update_general_settings(
    payload: GeneralSettings,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> GeneralSettings:
    before = get_system_settings_dict(db, actor.organization_id)
    updated = update_system_settings(db, payload.model_dump(), actor.organization_id, actor_user_id=actor.id)
    changes = _changed_values(before, updated)
    if changes:
        write_audit(
            db,
            action="settings_updated",
            entity="settings",
            actor_user_id=actor.id,
            metadata={"changes": changes},
        )
        db.commit()
    return GeneralSettings(**updated)


@router.get("/monthly-report-email", response_model=MonthlyReportEmailSettings)
def get_monthly_report_email_settings_endpoint(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> MonthlyReportEmailSettings:
    return MonthlyReportEmailSettings(**get_monthly_report_email_settings(db, actor.organization_id))


@router.put("/monthly-report-email", response_model=MonthlyReportEmailSettings)
def update_monthly_report_email_settings_endpoint(
    payload: MonthlyReportEmailSettings,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> MonthlyReportEmailSettings:
    before = get_monthly_report_email_settings(db, actor.organization_id)
    updated = update_monthly_report_email_settings(db, payload.model_dump(), actor.organization_id)
    changes = _changed_values(before, updated)
    if changes:
        write_audit(
            db,
            action="monthly_report_email_settings_updated",
            entity="settings",
            actor_user_id=actor.id,
            metadata={"changes": changes},
        )
        db.commit()
    return MonthlyReportEmailSettings(**updated)


def _resolved_ldap_settings(payload: LDAPSettings, db: Session, organization_id: int) -> dict[str, str]:
    stored = get_ldap_settings(db, organization_id, include_password=True)
    data = {
        "server": payload.server or stored.get("server") or "",
        "bind_dn": payload.bind_dn or stored.get("bind_dn") or "",
        "bind_password": payload.bind_password or stored.get("bind_password") or "",
        "search_base": payload.search_base or stored.get("search_base") or "",
    }
    if any(not value.strip() for value in data.values()):
        raise ValueError("Configuracao LDAP incompleta. Informe servidor, DN, senha e base de pesquisa.")
    return data


@router.get("/ldap", response_model=LDAPSettingsRead)
def get_ldap_settings_endpoint(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> LDAPSettingsRead:
    return LDAPSettingsRead(**get_ldap_settings(db, actor.organization_id))


@router.put("/ldap", response_model=LDAPSettingsRead)
def update_ldap_settings_endpoint(
    payload: LDAPSettings,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> LDAPSettingsRead:
    before = get_ldap_settings(db, actor.organization_id)
    updated = update_ldap_settings(db, payload.model_dump(exclude_unset=True), actor.organization_id)
    changes = _changed_values(before, updated)
    if changes:
        write_audit(
            db,
            action="ldap_settings_updated",
            entity="settings",
            actor_user_id=actor.id,
            metadata={"changes": changes},
        )
        db.commit()
    return LDAPSettingsRead(**updated)


@router.post("/ldap/test")
def test_ldap_endpoint(
    payload: LDAPSettings,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    try:
        ldap_settings = _resolved_ldap_settings(payload, db, actor.organization_id)
        test_ldap_connection(
            server=ldap_settings["server"],
            bind_dn=ldap_settings["bind_dn"],
            bind_password=ldap_settings["bind_password"],
        )
        return {"success": True, "message": "Conexão com LDAP realizada com sucesso"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/ldap/sync")
def sync_ldap_endpoint(
    payload: LDAPSettings,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    try:
        ldap_settings = _resolved_ldap_settings(payload, db, actor.organization_id)
        result = sync_ldap_users(
            db=db,
            server=ldap_settings["server"],
            bind_dn=ldap_settings["bind_dn"],
            bind_password=ldap_settings["bind_password"],
            search_base=ldap_settings["search_base"],
            organization_id=actor.organization_id,
        )
        write_audit(
            db,
            action="ldap_sync_performed",
            entity="users",
            entity_id=actor.id,
            actor_user_id=actor.id,
            metadata={
                "server": ldap_settings["server"],
                "new_users": result.get("new_users", 0),
                "total_synced": result.get("total_synced", 0)
            }
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
