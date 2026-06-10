from datetime import datetime, timezone
import re
import os
import shutil
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.department import Department
from app.models.print_job import PrintJob, JobStatus
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate, PrintJobDecision, PrintJobRead
from app.services.audit_service import write_audit
from app.services.print_job_service import register_print_job
from app.services.settings_service import get_system_settings_dict

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _can_operate_job(actor: User, job: PrintJob) -> bool:
    return job.user_id == actor.id or actor.role in (UserRole.admin, UserRole.manager)


def _validate_job_filters(
    db: Session,
    organization_id: int,
    *,
    user_id: int | None,
    department_id: int | None,
    printer_id: int | None,
) -> None:
    if user_id is not None and not db.query(User.id).filter(User.organization_id == organization_id, User.id == user_id).first():
        raise HTTPException(status_code=404, detail="Usuario do filtro nao encontrado")
    if department_id is not None and not db.query(Department.id).filter(Department.organization_id == organization_id, Department.id == department_id).first():
        raise HTTPException(status_code=404, detail="Departamento do filtro nao encontrado")
    if printer_id is not None and not db.query(Printer.id).filter(Printer.organization_id == organization_id, Printer.id == printer_id).first():
        raise HTTPException(status_code=404, detail="Impressora do filtro nao encontrada")


def _validate_date_range(date_from: datetime | None, date_to: datetime | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="Periodo invalido: data inicial maior que data final")


@router.get("", response_model=list[PrintJobRead])
def list_jobs(
    user_id: int | None = Query(default=None),
    department_id: int | None = Query(default=None),
    printer_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[PrintJobRead]:
    _validate_job_filters(
        db,
        actor.organization_id,
        user_id=user_id,
        department_id=department_id,
        printer_id=printer_id,
    )
    _validate_date_range(date_from, date_to)
    query = (
        db.query(PrintJob)
        .join(User, User.id == PrintJob.user_id)
        .join(Printer, Printer.id == PrintJob.printer_id)
        .filter(
            PrintJob.organization_id == actor.organization_id,
            User.organization_id == actor.organization_id,
            Printer.organization_id == actor.organization_id,
        )
    )
    if user_id:
        query = query.filter(PrintJob.user_id == user_id)
    if department_id:
        query = query.outerjoin(Department).filter(User.department_id == department_id)
    if printer_id:
        query = query.filter(PrintJob.printer_id == printer_id)
    if date_from:
        query = query.filter(PrintJob.submitted_at >= date_from)
    if date_to:
        query = query.filter(PrintJob.submitted_at <= date_to)

    jobs = query.order_by(PrintJob.submitted_at.desc()).limit(500).all()
    return [
        PrintJobRead(
            id=job.id,
            username=job.user.username,
            user_full_name=job.user.full_name,
            department_id=job.user.department_id,
            department_name=job.user.department.name if job.user.department else None,
            printer_name=job.printer.name,
            pages=job.pages,
            is_color=job.is_color,
            cost=job.cost,
            status=job.status,
            reason=job.reason,
            submitted_at=job.submitted_at,
            document_name=job.document_name,
            computer_name=job.computer_name,
            queue_name=job.queue_name,
            policy_name=job.policy_name,
            policy_action=job.policy_action,
        )
        for job in jobs
    ]


@router.post("", response_model=PrintJobDecision)
def create_job(
    payload: PrintJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> PrintJobDecision:
    try:
        return register_print_job(db, payload, current_user.organization_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agent-actions")
def get_agent_actions(
    job_keys: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> dict[str, str]:
    actions = {}
    if not job_keys:
        return actions
        
    keys = job_keys.split(",")
    for key in keys:
        if ":" not in key:
            continue
        printer_name, ext_id = key.split(":", 1)
        job = (
            db.query(PrintJob)
            .join(Printer)
            .filter(
                PrintJob.organization_id == current_user.organization_id,
                Printer.organization_id == current_user.organization_id,
                PrintJob.external_job_id == ext_id,
                or_(PrintJob.queue_name == printer_name, Printer.name == printer_name),
            )
            .order_by(PrintJob.id.desc())
            .first()
        )
        if not job:
            actions[key] = "delete"
        elif job.status in (JobStatus.released, JobStatus.authorized):
            actions[key] = "resume"
        elif job.status in (JobStatus.cancelled, JobStatus.blocked):
            actions[key] = "delete"
        else:
            actions[key] = "hold"
            
    return actions


@router.post("/{job_id}/release", response_model=PrintJobDecision)
def release_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.manager, UserRole.user)),
) -> PrintJobDecision:
    job = db.query(PrintJob).filter(PrintJob.organization_id == current_user.organization_id, PrintJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Trabalho não encontrado")
        
    if not _can_operate_job(current_user, job):
        raise HTTPException(status_code=403, detail="Permissão negada")
        
    if job.status != JobStatus.pending_release:
        raise HTTPException(status_code=400, detail="Trabalho não está pendente de liberação")
        
    from app.services.quota_service import get_or_create_current_quota, can_consume
    from app.services.settings_service import get_system_settings_dict
    
    quota = get_or_create_current_quota(db, job.user, job.submitted_at)
    sys_settings = get_system_settings_dict(db, current_user.organization_id)
    blocking_enabled = sys_settings["blocking_enabled"]
    
    authorized_pages = can_consume(quota, job.pages)
    authorized_balance = quota.remaining_balance >= job.cost
    
    if blocking_enabled and (not authorized_pages or not authorized_balance):
        job.status = JobStatus.blocked
        job.reason = "Cota ou saldo insuficientes no momento da liberação"
        write_audit(
            db,
            action="print_job_blocked",
            entity="print_jobs",
            entity_id=job.id,
            actor_user_id=current_user.id,
            metadata={
                "job_username": job.user.username,
                "actor_role": current_user.role.value,
                "printer": job.printer.name,
                "pages": job.pages,
                "cost": job.cost,
                "remaining_pages": quota.remaining_pages,
                "remaining_balance": quota.remaining_balance,
                "reason": job.reason,
                "blocked_at_release": True,
            },
        )
        db.commit()
        db.refresh(job)
        return PrintJobDecision(
            job_id=job.id,
            status=job.status,
            authorized=False,
            remaining_pages=quota.remaining_pages,
            remaining_balance=quota.remaining_balance,
            reason=job.reason,
            policy_name=job.policy_name,
            policy_action=job.policy_action,
        )
        
    quota.used_pages += job.pages
    quota.used_balance += job.cost
    job.status = JobStatus.released
    write_audit(
        db,
        action="print_job_released",
        entity="print_jobs",
        entity_id=job.id,
        actor_user_id=current_user.id,
        metadata={
            "job_username": job.user.username,
            "actor_role": current_user.role.value,
            "printer": job.printer.name,
            "pages": job.pages,
        },
    )
    db.commit()
    db.refresh(job)
    return PrintJobDecision(
        job_id=job.id,
        status=job.status,
        authorized=True,
        remaining_pages=quota.remaining_pages,
        remaining_balance=quota.remaining_balance,
        reason=job.reason,
        policy_name=job.policy_name,
        policy_action=job.policy_action,
    )


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.manager, UserRole.user)),
) -> dict:
    job = db.query(PrintJob).filter(PrintJob.organization_id == current_user.organization_id, PrintJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Trabalho não encontrado")
        
    if not _can_operate_job(current_user, job):
        raise HTTPException(status_code=403, detail="Permissão negada")
        
    if job.status != JobStatus.pending_release:
        raise HTTPException(status_code=400, detail="Trabalho não está pendente de liberação")
        
    job.status = JobStatus.cancelled
    write_audit(
        db,
        action="print_job_cancelled",
        entity="print_jobs",
        entity_id=job.id,
        actor_user_id=current_user.id,
        metadata={
            "job_username": job.user.username,
            "actor_role": current_user.role.value,
            "printer": job.printer.name,
            "pages": job.pages,
        },
    )
    job.reason = "Cancelado pelo usuário"
    db.commit()
    return {"status": "cancelled", "job_id": job.id}


# --- Web Print Support ---

def get_pdf_page_count(file_content: bytes) -> int:
    try:
        pages = len(re.findall(rb'/Type\s*/Page\b', file_content))
        if pages > 0:
            return pages
        matches = re.findall(rb'/Count\s+(\d+)', file_content)
        if matches:
            return max(int(m) for m in matches)
    except Exception:
        pass
    return 1


def _web_print_enabled(db: Session, organization_id: int) -> bool:
    return bool(get_system_settings_dict(db, organization_id)["web_print_enabled"])


def _ensure_web_print_enabled(db: Session, organization_id: int) -> None:
    if not _web_print_enabled(db, organization_id):
        raise HTTPException(status_code=403, detail="Modulo Web Print desativado")


def _clean_web_print_filename(filename: str | None) -> str:
    name = Path((filename or "").replace("\\", "/")).name.strip()
    if not name or not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF")
    if len(name) > 255:
        raise HTTPException(status_code=400, detail="Nome do arquivo PDF muito longo")
    return name


def _ensure_pdf_content(file_content: bytes) -> None:
    if not file_content or not file_content.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Arquivo PDF invalido")


@router.post("/web-print", response_model=PrintJobDecision)
def web_print_endpoint(
    file: UploadFile = File(...),
    printer_id: int = Form(...),
    is_color: bool = Form(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.manager, UserRole.user)),
) -> PrintJobDecision:
    _ensure_web_print_enabled(db, current_user.organization_id)

    # 1. Resolve printer
    printer = db.query(Printer).filter(Printer.organization_id == current_user.organization_id, Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
        
    # 2. Read PDF contents to temp location and parse page count
    try:
        file_content = file.file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Erro ao ler arquivo enviado") from exc

    document_name = _clean_web_print_filename(file.filename)
    _ensure_pdf_content(file_content)
    page_count = get_pdf_page_count(file_content)
    
    # 3. Create temp file inside uploads folder to preserve data
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    # Register the print job using the service
    payload = PrintJobCreate(
        username=current_user.username,
        printer_name=printer.name,
        pages=page_count,
        is_color=is_color,
        external_job_id=f"webprint_pending_{uuid4().hex}",
        document_name=document_name,
        submitted_at=datetime.now(timezone.utc),
    )
    
    try:
        decision = register_print_job(db, payload, current_user.organization_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
        
    # If job is created and not blocked, save the actual file using job_id
    if decision.authorized or decision.status == JobStatus.pending_release:
        file_path = uploads_dir / f"webprint_{decision.job_id}.pdf"
        try:
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            # Update the external_job_id to map to the file
            job = db.query(PrintJob).filter(PrintJob.organization_id == current_user.organization_id, PrintJob.id == decision.job_id).first()
            if job:
                job.external_job_id = f"webprint_{decision.job_id}"
                db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail="Erro ao salvar o arquivo no servidor") from exc
    return decision


@router.get("/agent-web-prints")
def get_agent_web_prints(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> list[dict]:
    if not _web_print_enabled(db, current_user.organization_id):
        return []

    # Query all released web-prints that are not yet printed
    # Web print jobs have external_job_id pattern: webprint_{job_id}
    jobs = (
        db.query(PrintJob)
        .join(Printer)
        .filter(
            PrintJob.organization_id == current_user.organization_id,
            Printer.organization_id == current_user.organization_id,
            PrintJob.status.in_([JobStatus.released, JobStatus.authorized]),
            PrintJob.external_job_id.like("webprint_%"),
            ~PrintJob.external_job_id.like("webprint_printed_%")
        )
        .all()
    )
    return [
        {
            "id": job.id,
            "printer_name": job.printer.name,
            "filename": job.document_name,
            "download_url": f"/jobs/{job.id}/download",
            "is_color": job.is_color,
            "pages": job.pages,
        }
        for job in jobs
    ]


@router.get("/{job_id}/download")
def download_web_print_file(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> FileResponse:
    _ensure_web_print_enabled(db, current_user.organization_id)

    job = db.query(PrintJob).filter(PrintJob.organization_id == current_user.organization_id, PrintJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Trabalho de impressão não encontrado")
        
    is_pending_web_print = bool(
        job.external_job_id
        and job.external_job_id.startswith("webprint_")
        and not job.external_job_id.startswith("webprint_printed_")
    )
    if not is_pending_web_print:
        raise HTTPException(status_code=400, detail="Trabalho nao e um Web Print pendente para download")
    if job.status not in (JobStatus.released, JobStatus.authorized):
        raise HTTPException(status_code=400, detail="Web Print ainda nao foi liberado para download")

    file_path = Path("uploads") / f"webprint_{job.id}.pdf"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo correspondente não encontrado")
        
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=job.document_name or f"webprint_{job.id}.pdf"
    )


@router.post("/{job_id}/confirm-web-printed")
def confirm_web_printed(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.agent, UserRole.admin)),
) -> dict:
    _ensure_web_print_enabled(db, current_user.organization_id)

    job = db.query(PrintJob).filter(PrintJob.organization_id == current_user.organization_id, PrintJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Trabalho não encontrado")
        
    # Mark it as printed by renaming the external_job_id
    if job.external_job_id and job.external_job_id.startswith("webprint_") and not job.external_job_id.startswith("webprint_printed_"):
        if job.status not in (JobStatus.released, JobStatus.authorized):
            raise HTTPException(status_code=400, detail="Web Print ainda nao foi liberado para impressao")
        job.external_job_id = f"webprint_printed_{job.id}"
        write_audit(
            db,
            action="web_print_confirmed",
            entity="print_jobs",
            entity_id=job.id,
            actor_user_id=current_user.id,
            metadata={
                "job_username": job.user.username if job.user else None,
                "actor_role": current_user.role.value,
                "printer": job.printer.name if job.printer else None,
                "document_name": job.document_name,
                "pages": job.pages,
                "is_color": job.is_color,
            },
        )
        db.commit()
        return {"success": True, "message": "Impressão confirmada"}
        
    return {"success": False, "message": "Trabalho não é uma impressão web pendente"}
