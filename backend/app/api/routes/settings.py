from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.user import User, UserRole
from app.schemas.settings import LDAPSettings
from app.services.ldap_service import test_ldap_connection, sync_ldap_users
from app.services.audit_service import write_audit

router = APIRouter(prefix="/settings", tags=["settings"])

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
            search_base=payload.search_base
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
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
