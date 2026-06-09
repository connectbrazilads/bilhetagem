from app.core.database import SessionLocal, engine
from app.models import audit_log, department, print_agent, print_job, printer, printer_alias, quota, user, system_setting  # noqa: F401
from app.models.base import Base
from app.models.user import UserRole
from app.seed import ensure_user
from app.core.config import settings


def initialize_lite_database() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    Base.metadata.create_all(bind=engine)
    _ensure_lite_schema()
    db = SessionLocal()
    try:
        ensure_user(
            db,
            username=settings.initial_admin_username,
            password=settings.initial_admin_password,
            role=UserRole.admin,
            full_name="Administrador",
        )
        ensure_user(
            db,
            username=settings.initial_agent_username,
            password=settings.initial_agent_password,
            role=UserRole.admin,
            full_name="Agente Windows",
        )
        db.commit()
    finally:
        db.close()


def _ensure_lite_schema() -> None:
    with engine.begin() as conn:
        existing_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(printers)").fetchall()}
        if "toner_levels" not in existing_columns:
            conn.exec_driver_sql("ALTER TABLE printers ADD COLUMN toner_levels JSON")
        job_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(print_jobs)").fetchall()}
        if "printer_alias_id" not in job_columns:
            conn.exec_driver_sql("ALTER TABLE print_jobs ADD COLUMN printer_alias_id INTEGER")
        if "agent_id" not in job_columns:
            conn.exec_driver_sql("ALTER TABLE print_jobs ADD COLUMN agent_id INTEGER")
        if "computer_name" not in job_columns:
            conn.exec_driver_sql("ALTER TABLE print_jobs ADD COLUMN computer_name VARCHAR(180)")
        if "queue_name" not in job_columns:
            conn.exec_driver_sql("ALTER TABLE print_jobs ADD COLUMN queue_name VARCHAR(180)")
