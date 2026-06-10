from pathlib import Path

from sqlalchemy import create_engine

from app import lite_init


def _columns(engine, table_name: str) -> set[str]:
    with engine.begin() as conn:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()}


def _organization_ids(engine, table_name: str) -> list[int | None]:
    with engine.begin() as conn:
        return [row[0] for row in conn.exec_driver_sql(f"SELECT organization_id FROM {table_name}").fetchall()]


def test_lite_schema_adds_organization_id_to_commercial_tables(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "legacy-lite.db"
    engine = create_engine(f"sqlite:///{database_path}")
    tables = {
        "departments": "id INTEGER PRIMARY KEY, name VARCHAR(120)",
        "printers": "id INTEGER PRIMARY KEY, name VARCHAR(180)",
        "users": "id INTEGER PRIMARY KEY, username VARCHAR(120), full_name VARCHAR(180), role VARCHAR(40)",
        "quotas": "id INTEGER PRIMARY KEY",
        "print_jobs": "id INTEGER PRIMARY KEY",
        "audit_logs": "id INTEGER PRIMARY KEY",
        "print_agents": "id INTEGER PRIMARY KEY",
        "printer_aliases": "id INTEGER PRIMARY KEY",
        "system_settings": "id INTEGER PRIMARY KEY",
        "agent_queue_actions": "id INTEGER PRIMARY KEY",
        "print_policies": "id INTEGER PRIMARY KEY",
        "monthly_closings": "id INTEGER PRIMARY KEY",
        "agent_logs": "id INTEGER PRIMARY KEY",
    }
    with engine.begin() as conn:
        for table_name, columns in tables.items():
            conn.exec_driver_sql(f"CREATE TABLE {table_name} ({columns})")
            if table_name == "users":
                conn.exec_driver_sql("INSERT INTO users (id, username, full_name, role) VALUES (1, 'agent', 'Agente Windows', 'user')")
            else:
                conn.exec_driver_sql(f"INSERT INTO {table_name} (id) VALUES (1)")

    monkeypatch.setattr(lite_init, "engine", engine)

    lite_init._ensure_lite_schema()

    for table_name in tables:
        assert "organization_id" in _columns(engine, table_name), table_name
        assert _organization_ids(engine, table_name) == [1], table_name
