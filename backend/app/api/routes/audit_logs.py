from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.schemas.audit import AuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    action: str | None = Query(default=None, max_length=80),
    entity: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[AuditLogRead]:
    query = (
        db.query(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .filter(AuditLog.organization_id == actor.organization_id)
    )
    if action:
        query = query.filter(AuditLog.action == action)
    if entity:
        query = query.filter(AuditLog.entity == entity)

    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
    return [
        AuditLogRead(
            id=log.id,
            actor_user_id=log.actor_user_id,
            actor_username=username,
            action=log.action,
            entity=log.entity,
            entity_id=log.entity_id,
            metadata=log.log_metadata or {},
            created_at=log.created_at,
        )
        for log, username in rows
    ]
