import os
import subprocess
import sys
from pathlib import Path


def test_postgres_migration_sql_does_not_duplicate_enum_creation():
    backend_dir = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+psycopg://user:pass@localhost/printbilling_test"
    env.setdefault("SECRET_KEY", "test-secret-key-with-enough-length")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    sql = result.stdout
    for enum_name in (
        "userrole",
        "jobstatus",
        "agentqueueactiontype",
        "agentqueueactionstatus",
        "policyruletype",
        "policyaction",
    ):
        assert sql.count(f"CREATE TYPE {enum_name}") == 1, enum_name
    assert "ALTER TYPE agentqueueactiontype ADD VALUE IF NOT EXISTS 'restore_queue'" in sql
