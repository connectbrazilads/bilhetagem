from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.print_agent import PrintAgent
from app.models.print_job import PrintJob
from app.models.printer_alias import PrinterAlias
from app.models.user import User
from app.models.user import UserRole
from app.schemas.agent import AgentHeartbeatPayload, AgentRecentJobRead, AgentVersionRead, PrintAgentRead

router = APIRouter(prefix="/agent", tags=["agent"])


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split("."):
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def _is_newer(latest: str, current: str | None) -> bool:
    if not current:
        return True
    latest_parts = _version_tuple(latest)
    current_parts = _version_tuple(current)
    size = max(len(latest_parts), len(current_parts))
    latest_parts = latest_parts + (0,) * (size - len(latest_parts))
    current_parts = current_parts + (0,) * (size - len(current_parts))
    return latest_parts > current_parts


def _agent_file() -> Path:
    return Path(settings.agent_download_dir) / settings.agent_download_filename


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_alias_name(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.strip().lower().split()) or None


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()[:45] or None
    if request.client:
        return request.client.host[:45]
    return None


def _agent_status(agent: PrintAgent, now: datetime | None = None) -> tuple[bool, str]:
    if not agent.last_seen_at:
        return False, "Nunca conectado"
    now = now or datetime.now(timezone.utc)
    last_seen = agent.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    if now - last_seen <= timedelta(minutes=3):
        if agent.last_error:
            return True, "Online com alerta"
        return True, "Online"
    return False, "Offline"


def _recent_jobs(db: Session, agent: PrintAgent) -> list[AgentRecentJobRead]:
    jobs = (
        db.query(PrintJob)
        .filter(PrintJob.organization_id == agent.organization_id, PrintJob.agent_id == agent.id)
        .order_by(PrintJob.submitted_at.desc(), PrintJob.id.desc())
        .limit(10)
        .all()
    )
    return [
        AgentRecentJobRead(
            id=job.id,
            username=job.user.username if job.user else "-",
            printer_name=job.printer.name if job.printer else job.queue_name or "-",
            document_name=job.document_name,
            pages=job.pages,
            is_color=job.is_color,
            status=job.status.value if hasattr(job.status, "value") else str(job.status),
            submitted_at=job.submitted_at,
        )
        for job in jobs
    ]


def _agent_to_read(agent: PrintAgent, include_jobs: bool = False, db: Session | None = None) -> PrintAgentRead:
    is_online, status_text = _agent_status(agent)
    return PrintAgentRead(
        id=agent.id,
        agent_uid=agent.agent_uid,
        computer_name=agent.computer_name,
        os_user=agent.os_user,
        version=agent.version,
        ip_address=agent.ip_address,
        capture_mode=agent.capture_mode,
        event_log_enabled=agent.event_log_enabled,
        auto_update_enabled=agent.auto_update_enabled,
        last_error=agent.last_error,
        last_seen_at=agent.last_seen_at,
        created_at=agent.created_at,
        is_online=is_online,
        status=status_text,
        aliases=list(agent.aliases),
        recent_jobs=_recent_jobs(db, agent) if include_jobs and db is not None else [],
    )


@router.get("/version", response_model=AgentVersionRead)
def agent_version(
    current_version: str | None = Query(default=None),
    _: User = Depends(get_current_user),
) -> AgentVersionRead:
    file_exists = _agent_file().exists()
    return AgentVersionRead(
        latest_version=settings.agent_latest_version,
        update_available=file_exists and _is_newer(settings.agent_latest_version, current_version),
        mandatory=False,
        download_url="/agent/download" if file_exists else None,
    )


@router.get("/download")
def download_agent_update(_: User = Depends(get_current_user)) -> FileResponse:
    path = _agent_file()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Atualizacao do agent nao publicada")
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=settings.agent_download_filename,
    )


@router.post("/heartbeat", response_model=PrintAgentRead)
def agent_heartbeat(
    payload: AgentHeartbeatPayload,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> PrintAgentRead:
    now = datetime.now(timezone.utc)
    agent_uid = _clean_optional(payload.agent_uid)
    if not agent_uid:
        raise HTTPException(status_code=422, detail="agent_uid obrigatorio")

    agent = (
        db.query(PrintAgent)
        .options(selectinload(PrintAgent.aliases))
        .filter(PrintAgent.organization_id == actor.organization_id, PrintAgent.agent_uid == agent_uid)
        .first()
    )
    if not agent:
        agent = PrintAgent(organization_id=actor.organization_id, agent_uid=agent_uid)
        db.add(agent)
        db.flush()

    agent.computer_name = _clean_optional(payload.computer_name)
    agent.os_user = _clean_optional(payload.os_user)
    agent.version = _clean_optional(payload.version)
    agent.ip_address = _client_ip(request)
    agent.capture_mode = _clean_optional(payload.capture_mode)
    agent.event_log_enabled = payload.event_log_enabled
    agent.auto_update_enabled = payload.auto_update_enabled
    agent.last_error = _clean_optional(payload.last_error)
    agent.last_seen_at = now

    existing_aliases = {
        alias.queue_name: alias
        for alias in db.query(PrinterAlias)
        .filter(PrinterAlias.organization_id == actor.organization_id, PrinterAlias.agent_id == agent.id)
        .all()
    }
    for queue in payload.queues:
        queue_name = queue.queue_name.strip()
        alias = existing_aliases.get(queue_name)
        if not alias:
            alias = PrinterAlias(
                organization_id=actor.organization_id,
                agent_id=agent.id,
                queue_name=queue_name,
            )
            db.add(alias)
            db.flush()
            existing_aliases[queue_name] = alias
        alias.normalized_queue_name = _normalize_alias_name(queue_name)
        alias.computer_name = agent.computer_name
        alias.driver_name = _clean_optional(queue.driver_name)
        alias.port_name = _clean_optional(queue.port_name)
        alias.connection_type = _clean_optional(queue.connection_type)
        alias.ip_address = _clean_optional(queue.ip_address)
        alias.serial_number = _clean_optional(queue.serial_number)
        alias.device_id = _clean_optional(queue.device_id)
        alias.fingerprint = _clean_optional(queue.fingerprint)
        alias.last_seen_at = now

    db.commit()
    agent = (
        db.query(PrintAgent)
        .options(selectinload(PrintAgent.aliases))
        .filter(PrintAgent.id == agent.id, PrintAgent.organization_id == actor.organization_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent nao encontrado")
    return _agent_to_read(agent)


@router.get("/agents", response_model=list[PrintAgentRead])
def list_agents(
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[PrintAgentRead]:
    agents = (
        db.query(PrintAgent)
        .options(selectinload(PrintAgent.aliases))
        .filter(PrintAgent.organization_id == actor.organization_id)
        .order_by(PrintAgent.last_seen_at.desc().nullslast(), PrintAgent.computer_name, PrintAgent.id)
        .all()
    )
    return [_agent_to_read(agent) for agent in agents]


@router.get("/agents/{agent_id}", response_model=PrintAgentRead)
def get_agent_detail(
    agent_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> PrintAgentRead:
    agent = (
        db.query(PrintAgent)
        .options(selectinload(PrintAgent.aliases), selectinload(PrintAgent.aliases).selectinload(PrinterAlias.printer))
        .filter(PrintAgent.organization_id == actor.organization_id, PrintAgent.id == agent_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent nao encontrado")
    return _agent_to_read(agent, include_jobs=True, db=db)
