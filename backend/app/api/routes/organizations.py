from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.print_agent import PrintAgent
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.services.audit_service import write_audit
from app.services.organization_service import DEFAULT_ORGANIZATION_SLUG

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _can_manage_all(actor: User) -> bool:
    return bool(actor.organization and actor.organization.slug == DEFAULT_ORGANIZATION_SLUG and actor.role == UserRole.admin)


def _agent_is_online(agent: PrintAgent, now: datetime) -> bool:
    if not agent.last_seen_at:
        return False
    last_seen = agent.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return now - last_seen <= timedelta(minutes=3)


def _changed_values(before: dict, after: dict) -> dict:
    changes = {}
    for key, after_value in after.items():
        before_value = before.get(key)
        if before_value != after_value:
            changes[key] = {"before": before_value, "after": after_value}
    return changes


def _scoped_jobs_query(db: Session, organization_id: int):
    return (
        db.query(PrintJob)
        .join(User, User.id == PrintJob.user_id)
        .join(Printer, Printer.id == PrintJob.printer_id)
        .filter(
            PrintJob.organization_id == organization_id,
            User.organization_id == organization_id,
            Printer.organization_id == organization_id,
        )
    )


def _organization_read(db: Session, organization: Organization) -> OrganizationRead:
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    agents = db.query(PrintAgent).filter(PrintAgent.organization_id == organization.id).all()
    online_agents = sum(1 for agent in agents if _agent_is_online(agent, now))
    monthly_billable_query = _scoped_jobs_query(db, organization.id).filter(
        PrintJob.submitted_at >= month_start,
        PrintJob.status.in_([JobStatus.authorized, JobStatus.released]),
    )
    pages_month, cost_month = (
        monthly_billable_query
        .with_entities(
            func.coalesce(func.sum(PrintJob.pages), 0),
            func.coalesce(func.sum(PrintJob.cost), 0.0),
        )
        .one()
    )
    jobs_month = monthly_billable_query.count()
    return OrganizationRead(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        is_active=organization.is_active,
        created_at=organization.created_at,
        users_count=db.query(User).filter(User.organization_id == organization.id).count(),
        printers_count=db.query(Printer).filter(Printer.organization_id == organization.id).count(),
        agents_count=len(agents),
        online_agents_count=online_agents,
        offline_agents_count=len(agents) - online_agents,
        jobs_count=_scoped_jobs_query(db, organization.id).count(),
        jobs_month=int(jobs_month or 0),
        pages_month=int(pages_month or 0),
        cost_month=float(cost_month or 0.0),
    )


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> list[OrganizationRead]:
    if not _can_manage_all(actor):
        return [_organization_read(db, actor.organization)]
    organizations = db.query(Organization).order_by(Organization.name).all()
    return [_organization_read(db, organization) for organization in organizations]


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> OrganizationRead:
    if not _can_manage_all(actor):
        raise HTTPException(status_code=403, detail="Somente o admin da empresa padrao pode criar empresas")
    organization = Organization(name=payload.name, slug=payload.slug, is_active=payload.is_active)
    db.add(organization)
    try:
        db.flush()
        db.add_all(
            [
                User(
                    organization_id=organization.id,
                    username=payload.admin_username,
                    full_name="Administrador",
                    password_hash=hash_password(payload.admin_password),
                    role=UserRole.admin,
                    is_active=True,
                ),
                User(
                    organization_id=organization.id,
                    username=payload.agent_username,
                    full_name="Agente Windows",
                    password_hash=hash_password(payload.agent_password),
                    role=UserRole.agent,
                    is_active=True,
                ),
            ]
        )
        db.flush()
        write_audit(
            db,
            action="organization_created",
            entity="organizations",
            entity_id=organization.id,
            actor_user_id=actor.id,
            metadata={
                "name": organization.name,
                "slug": organization.slug,
                "admin_username": payload.admin_username,
                "agent_username": payload.agent_username,
            },
            organization_id=actor.organization_id,
        )
        db.commit()
        db.refresh(organization)
        return _organization_read(db, organization)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Empresa ja cadastrada") from exc


@router.put("/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: int,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin)),
) -> OrganizationRead:
    if not _can_manage_all(actor) and actor.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="Permissao insuficiente")
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if payload.is_active is False and organization.id == actor.organization_id:
        raise HTTPException(status_code=400, detail="Nao e possivel desativar a empresa em uso pelo usuario logado")

    before = {"name": organization.name, "is_active": organization.is_active}
    if payload.name is not None:
        organization.name = payload.name
    if payload.is_active is not None:
        organization.is_active = payload.is_active

    try:
        changes = _changed_values(before, {"name": organization.name, "is_active": organization.is_active})
        if changes:
            write_audit(
                db,
                action="organization_updated",
                entity="organizations",
                entity_id=organization.id,
                actor_user_id=actor.id,
                metadata={"changes": changes},
                organization_id=actor.organization_id,
            )
        db.commit()
        db.refresh(organization)
        return _organization_read(db, organization)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Nome de empresa ja cadastrado") from exc
