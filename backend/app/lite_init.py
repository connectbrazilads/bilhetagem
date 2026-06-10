from app.core.database import SessionLocal, engine
from app.models import agent_log, agent_queue_action, audit_log, department, monthly_closing, organization, print_agent, print_job, print_policy, printer, printer_alias, quota, user, system_setting  # noqa: F401
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
            role=UserRole.agent,
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
                "CREATE TABLE organizations (id INTEGER PRIMARY KEY, name VARCHAR(180) NOT NULL UNIQUE, slug VARCHAR(120) NOT NULL UNIQUE, is_active BOOLEAN NOT NULL DEFAULT 1, billing_plan VARCHAR(40) NOT NULL DEFAULT 'starter', billing_status VARCHAR(40) NOT NULL DEFAULT 'trial', contracted_printer_limit INTEGER NOT NULL DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO organizations (id, name, slug, is_active) VALUES (1, 'Empresa Padrao', 'default', 1)"
            )
        organization_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(organizations)").fetchall()}
        if "billing_plan" not in organization_columns:
            conn.exec_driver_sql("ALTER TABLE organizations ADD COLUMN billing_plan VARCHAR(40) NOT NULL DEFAULT 'starter'")
        if "billing_status" not in organization_columns:
            conn.exec_driver_sql("ALTER TABLE organizations ADD COLUMN billing_status VARCHAR(40) NOT NULL DEFAULT 'trial'")
        if "contracted_printer_limit" not in organization_columns:
            conn.exec_driver_sql("ALTER TABLE organizations ADD COLUMN contracted_printer_limit INTEGER NOT NULL DEFAULT 0")
        for table_name in (
            "departments",
            "printers",
            "users",
            "quotas",
            "print_jobs",
            "audit_logs",
            "print_agents",
            "printer_aliases",
            "system_settings",
            "agent_queue_actions",
            "print_policies",
            "monthly_closings",
            "agent_logs",
        ):
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
        users_exists = conn.exec_driver_sql(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users'"
        ).scalar()
        if users_exists:
            conn.exec_driver_sql("UPDATE users SET role = 'agent' WHERE lower(username) = 'agent' OR full_name = 'Agente Windows'")
        department_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(departments)").fetchall()}
        if "cost_center" not in department_columns:
            conn.exec_driver_sql("ALTER TABLE departments ADD COLUMN cost_center VARCHAR(120)")
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
        if "policy_id" not in job_columns:
            conn.exec_driver_sql("ALTER TABLE print_jobs ADD COLUMN policy_id INTEGER")
        if "policy_name" not in job_columns:
            conn.exec_driver_sql("ALTER TABLE print_jobs ADD COLUMN policy_name VARCHAR(180)")
        if "policy_action" not in job_columns:
            conn.exec_driver_sql("ALTER TABLE print_jobs ADD COLUMN policy_action VARCHAR(40)")
        agent_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(print_agents)").fetchall()}
        if "ip_address" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN ip_address VARCHAR(45)")
        if "capture_mode" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN capture_mode VARCHAR(40)")
        if "event_log_enabled" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN event_log_enabled BOOLEAN")
        if "auto_update_enabled" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN auto_update_enabled BOOLEAN")
        if "local_admin" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN local_admin BOOLEAN")
        if "last_error" not in agent_columns:
            conn.exec_driver_sql("ALTER TABLE print_agents ADD COLUMN last_error VARCHAR(500)")
        queue_actions_count = conn.exec_driver_sql(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='agent_queue_actions'"
        ).scalar()
        if not queue_actions_count:
            conn.exec_driver_sql(
                """
                CREATE TABLE agent_queue_actions (
                    id INTEGER PRIMARY KEY,
                    organization_id INTEGER NOT NULL DEFAULT 1,
                    agent_id INTEGER NOT NULL,
                    printer_id INTEGER,
                    requested_by_user_id INTEGER,
                    action_type VARCHAR(40) NOT NULL,
                    queue_name VARCHAR(180) NOT NULL,
                    driver_name VARCHAR(180),
                    port_name VARCHAR(180),
                    ip_address VARCHAR(45),
                    status VARCHAR(40) NOT NULL DEFAULT 'pending',
                    result_message VARCHAR(500),
                    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    dispatched_at DATETIME,
                    completed_at DATETIME
                )
                """
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_agent_queue_actions_agent_status ON agent_queue_actions (agent_id, status)"
            )
        policies_count = conn.exec_driver_sql(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='print_policies'"
        ).scalar()
        if not policies_count:
            conn.exec_driver_sql(
                """
                CREATE TABLE print_policies (
                    id INTEGER PRIMARY KEY,
                    organization_id INTEGER NOT NULL DEFAULT 1,
                    name VARCHAR(180) NOT NULL,
                    description VARCHAR(255),
                    priority INTEGER NOT NULL DEFAULT 100,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    rule_type VARCHAR(40) NOT NULL,
                    action VARCHAR(40) NOT NULL,
                    user_id INTEGER,
                    department_id INTEGER,
                    printer_id INTEGER,
                    printer_alias_id INTEGER,
                    queue_name VARCHAR(180),
                    max_pages INTEGER,
                    days_of_week VARCHAR(40),
                    start_time TIME,
                    end_time TIME,
                    message VARCHAR(255),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_print_policies_org_active_priority ON print_policies (organization_id, is_active, priority)"
            )
        closings_count = conn.exec_driver_sql(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='monthly_closings'"
        ).scalar()
        if not closings_count:
            conn.exec_driver_sql(
                """
                CREATE TABLE monthly_closings (
                    id INTEGER PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    total_jobs INTEGER NOT NULL DEFAULT 0,
                    billable_jobs INTEGER NOT NULL DEFAULT 0,
                    pending_jobs INTEGER NOT NULL DEFAULT 0,
                    blocked_jobs INTEGER NOT NULL DEFAULT 0,
                    total_pages INTEGER NOT NULL DEFAULT 0,
                    mono_pages INTEGER NOT NULL DEFAULT 0,
                    color_pages INTEGER NOT NULL DEFAULT 0,
                    blocked_pages INTEGER NOT NULL DEFAULT 0,
                    total_cost FLOAT NOT NULL DEFAULT 0,
                    snapshot JSON NOT NULL,
                    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    UNIQUE (organization_id, year, month)
                )
                """
            )
        agent_logs_count = conn.exec_driver_sql(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='agent_logs'"
        ).scalar()
        if not agent_logs_count:
            conn.exec_driver_sql(
                """
                CREATE TABLE agent_logs (
                    id INTEGER PRIMARY KEY,
                    organization_id INTEGER NOT NULL DEFAULT 1,
                    agent_id INTEGER NOT NULL,
                    level VARCHAR(20) NOT NULL,
                    message VARCHAR(1000) NOT NULL,
                    source VARCHAR(80),
                    occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    received_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_agent_logs_agent_received ON agent_logs (agent_id, received_at)"
            )
