from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.user import User, UserRole
from app.schemas.settings import LDAPSettings, GeneralSettings, MonthlyReportEmailSettings, OperationalSettings
from app.services.ldap_service import test_ldap_connection, sync_ldap_users
from app.services.settings_service import (
    get_monthly_report_email_settings,
    get_system_settings_dict,
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
    updated = update_system_settings(db, payload.model_dump(), actor.organization_id)
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


@router.post("/ldap/test")
def test_ldap_endpoint(
    payload: LDAPSettings,
    _: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    try:
        test_ldap_connection(
            server=payload.server,
            bind_dn=payload.bind_dn,
            bind_password=payload.bind_password
        )
        return {"success": True, "message": "Conexão com LDAP realizada com sucesso (MOCK)"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/ldap/sync")
def sync_ldap_endpoint(
    payload: LDAPSettings,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    try:
        result = sync_ldap_users(
            db=db,
            server=payload.server,
            bind_dn=payload.bind_dn,
            bind_password=payload.bind_password,
            search_base=payload.search_base,
            organization_id=actor.organization_id,
        )
        write_audit(
            db,
            action="ldap_sync_performed",
            entity="users",
            entity_id=actor.id,
            actor_user_id=actor.id,
            metadata={
                "server": payload.server,
                "new_users": result.get("new_users", 0),
                "total_synced": result.get("total_synced", 0)
            }
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
