from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def write_audit(
    db: Session,
    *,
    action: str,
    entity: str,
    entity_id: int | None = None,
    actor_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        action=action,
        entity=entity,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        log_metadata=metadata or {},
    )
    db.add(log)
    db.flush()
    return log
