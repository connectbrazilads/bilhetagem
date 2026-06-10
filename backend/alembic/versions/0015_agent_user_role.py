"""add agent user role

Revision ID: 0015_agent_user_role
Revises: 0014_agent_logs
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0015_agent_user_role"
down_revision: Union[str, None] = "0014_agent_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        context = op.get_context()
        with context.autocommit_block():
            op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'agent'")
    op.execute("UPDATE users SET role = 'agent' WHERE lower(username) = 'agent' OR full_name = 'Agente Windows'")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'agent'")
