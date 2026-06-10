from app.core.database import SessionLocal, engine
from app.models import audit_log, department, organization, print_agent, print_job, printer, printer_alias, quota, user, system_setting  # noqa: F401
from app.models.base import Base
from app.models.user import UserRole
from app.seed import ensure_user
from app.core.config import settings
from app.services.organization_service import get_or_create_default_organization


def initialize_lite_database() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    Base.metadata.create_all(bind=engine)
    _ensure_lite_schema()
    db = SessionLocal()
    try:
        get_or_create_default_organization(db)
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
        organization_count = conn.exec_driver_sql(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='organizations'"
        ).scalar()
        if not organization_count:
            conn.exec_driver_sql(
                "CREATE TABLE organizations (id INTEGER PRIMARY KEY, name VARCHAR(180) NOT NULL UNIQUE, slug VARCHAR(120) NOT NULL UNIQUE, is_active BOOLEAN NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO organizations (id, name, slug, is_active) VALUES (1, 'Empresa Padrao', 'default', 1)"
            )
        for table_name in ("departments", "printers", "users", "quotas", "print_jobs", "audit_logs", "print_agents", "printer_aliases", "system_settings"):
            exists = conn.exec_driver_sql(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).scalar()
            if not exists:
                continue
            columns = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()}
            if "organization_id" not in columns:
                conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN organization_id INTEGER")
                conn.exec_driver_sql(f"UPDATE {table_name} SET organization_id = 1 WHERE organization_id IS NULL")
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
        agent_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(print_agents)").fetchall()}
        if "ip_address" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN ip_address VARCHAR(45)")
        if "capture_mode" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN capture_mode VARCHAR(40)")
        if "event_log_enabled" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN event_log_enabled BOOLEAN")
        if "auto_update_enabled" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN auto_update_enabled BOOLEAN")
        if "last_error" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN last_error VARCHAR(500)")
