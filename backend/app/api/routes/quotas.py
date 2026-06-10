from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.quota import Quota
from app.models.user import User, UserRole
from app.schemas.quota import QuotaRead, QuotaUpdate
from app.services.audit_service import write_audit

router = APIRouter(prefix="/quotas", tags=["quotas"])


def _read_quota(quota: Quota) -> QuotaRead:
    return QuotaRead(
        id=quota.id,
        user_id=quota.user_id,
        username=quota.user.username,
        year=quota.year,
        month=quota.month,
        monthly_limit=quota.monthly_limit,
        used_pages=quota.used_pages,
        remaining_pages=quota.remaining_pages,
    )


@router.get("", response_model=list[QuotaRead])
def list_quotas(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[QuotaRead]:
    quotas = (
        db.query(Quota)
        .join(User)
        .filter(Quota.organization_id == actor.organization_id, User.organization_id == actor.organization_id)
        .order_by(Quota.year.desc(), Quota.month.desc(), User.username)
        .all()
    )
    return [_read_quota(quota) for quota in quotas]


@router.put("/{quota_id}", response_model=QuotaRead)
def update_quota(
    quota_id: int,
    payload: QuotaUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> QuotaRead:
    quota = db.query(Quota).filter(Quota.organization_id == actor.organization_id, Quota.id == quota_id).first()
    if not quota:
        raise HTTPException(status_code=404, detail="Cota não encontrada")
    quota.monthly_limit = payload.monthly_limit
    write_audit(db, action="quota_updated", entity="quotas", entity_id=quota.id, actor_user_id=actor.id)
    db.commit()
    db.refresh(quota)
    return _read_quota(quota)
