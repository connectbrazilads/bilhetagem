from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.services.audit_service import write_audit
from app.services.organization_service import DEFAULT_ORGANIZATION_SLUG

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _can_manage_all(actor: User) -> bool:
    return bool(actor.organization and actor.organization.slug == DEFAULT_ORGANIZATION_SLUG and actor.role == UserRole.admin)


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> list[Organization]:
    if not _can_manage_all(actor):
        return [actor.organization]
    return db.query(Organization).order_by(Organization.name).all()


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Organization:
    if not _can_manage_all(actor):
        raise HTTPException(status_code=403, detail="Somente o admin da empresa padrao pode criar empresas")
    organization = Organization(name=payload.name, slug=payload.slug, is_active=payload.is_active)
    db.add(organization)
    try:
        db.flush()
        write_audit(
            db,
            action="organization_created",
            entity="organizations",
            entity_id=organization.id,
            actor_user_id=actor.id,
            metadata={"name": organization.name, "slug": organization.slug},
            organization_id=actor.organization_id,
        )
        db.commit()
        db.refresh(organization)
        return organization
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Empresa ja cadastrada") from exc


@router.put("/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: int,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> Organization:
    if not _can_manage_all(actor) and actor.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="Permissao insuficiente")
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")

    if payload.name is not None:
        organization.name = payload.name
    if payload.is_active is not None:
        organization.is_active = payload.is_active

    try:
        write_audit(
            db,
            action="organization_updated",
            entity="organizations",
            entity_id=organization.id,
            actor_user_id=actor.id,
            metadata={"name": organization.name, "is_active": organization.is_active},
            organization_id=actor.organization_id,
        )
        db.commit()
        db.refresh(organization)
        return organization
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Nome de empresa ja cadastrado") from exc
