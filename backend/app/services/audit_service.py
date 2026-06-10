from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.organization_service import get_or_create_default_organization


def write_audit(
    db: Session,
    *,
    action: str,
    entity: str,
    entity_id: int | None = None,
    actor_user_id: int | None = None,
    organization_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    if organization_id is None and actor_user_id is not None:
        actor = db.get(User, actor_user_id)
        organization_id = actor.organization_id if actor else None
    if organization_id is None:
        organization_id = get_or_create_default_organization(db).id
    log = AuditLog(
        organization_id=organization_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        log_metadata=metadata or {},
    )
    db.add(log)
    db.flush()
    return log
