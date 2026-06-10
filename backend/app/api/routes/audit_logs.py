from datetime import datetime
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.schemas.audit import AuditLogFacets, AuditLogRead
from app.services.audit_service import write_audit

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


def _validate_date_range(date_from: datetime | None, date_to: datetime | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="Periodo invalido: data inicial maior que data final")


def _audit_query(
    db: Session,
    actor: User,
    *,
    action: str | None,
    entity: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
):
    query = (
        db.query(AuditLog, User.username)
        .outerjoin(User, and_(User.id == AuditLog.actor_user_id, User.organization_id == AuditLog.organization_id))
        .filter(AuditLog.organization_id == actor.organization_id)
    )
    if action:
        query = query.filter(AuditLog.action == action)
    if entity:
        query = query.filter(AuditLog.entity == entity)
    if date_from:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to:
        query = query.filter(AuditLog.created_at <= date_to)
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


def _to_read_model(log: AuditLog, username: str | None) -> AuditLogRead:
    return AuditLogRead(
        id=log.id,
        actor_user_id=log.actor_user_id,
        actor_username=username,
        action=log.action,
        entity=log.entity,
        entity_id=log.entity_id,
        metadata=log.log_metadata or {},
        created_at=log.created_at,
    )


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    action: str | None = Query(default=None, max_length=80),
    entity: str | None = Query(default=None, max_length=80),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[AuditLogRead]:
    _validate_date_range(date_from, date_to)
    rows = _audit_query(
        db,
        actor,
        action=action,
        entity=entity,
        date_from=date_from,
        date_to=date_to,
    ).limit(limit).all()
    return [_to_read_model(log, username) for log, username in rows]


@router.get("/facets", response_model=AuditLogFacets)
def list_audit_log_facets(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> AuditLogFacets:
    actions = (
        db.query(AuditLog.action)
        .filter(AuditLog.organization_id == actor.organization_id)
        .distinct()
        .order_by(AuditLog.action)
        .all()
    )
    entities = (
        db.query(AuditLog.entity)
        .filter(AuditLog.organization_id == actor.organization_id)
        .distinct()
        .order_by(AuditLog.entity)
        .all()
    )
    return AuditLogFacets(
        actions=[action for (action,) in actions],
        entities=[entity for (entity,) in entities],
    )


@router.get("/export")
def export_audit_logs(
    action: str | None = Query(default=None, max_length=80),
    entity: str | None = Query(default=None, max_length=80),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=10000),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> Response:
    _validate_date_range(date_from, date_to)
    rows = _audit_query(
        db,
        actor,
        action=action,
        entity=entity,
        date_from=date_from,
        date_to=date_to,
    ).limit(limit).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["data_hora", "ator", "acao", "entidade", "id_entidade", "detalhes"])
    for log, username in rows:
        writer.writerow(
            [
                log.created_at.isoformat(),
                username or "Sistema",
                log.action,
                log.entity,
                log.entity_id or "",
                json.dumps(log.log_metadata or {}, ensure_ascii=False),
            ]
        )

    write_audit(
        db,
        action="audit_logs_exported",
        entity="audit_logs",
        actor_user_id=actor.id,
        metadata={
            "rows": len(rows),
            "filters": {
                "action": action,
                "entity": entity,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "limit": limit,
            },
        },
    )
    db.commit()

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="auditoria.csv"'},
    )
