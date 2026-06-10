"""add agent health fields

Revision ID: 0010_agent_health
Revises: 0009_org_unique_constraints
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_agent_health"
down_revision: Union[str, None] = "0009_org_unique_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("print_agents", sa.Column("ip_address", sa.String(length=45), nullable=True))
    op.add_column("print_agents", sa.Column("capture_mode", sa.String(length=40), nullable=True))
    op.add_column("print_agents", sa.Column("event_log_enabled", sa.Boolean(), nullable=True))
    op.add_column("print_agents", sa.Column("auto_update_enabled", sa.Boolean(), nullable=True))
    op.add_column("print_agents", sa.Column("last_error", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("print_agents", "last_error")
    op.drop_column("print_agents", "auto_update_enabled")
    op.drop_column("print_agents", "event_log_enabled")
    op.drop_column("print_agents", "capture_mode")
    op.drop_column("print_agents", "ip_address")
