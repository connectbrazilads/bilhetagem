"""add agent enrollment keys

Revision ID: 0020_agent_enrollment_keys
Revises: 0019_department_cost_center
Create Date: 2026-06-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020_agent_enrollment_keys"
down_revision: Union[str, None] = "0019_department_cost_center"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("agent_enrollment_token_hash", sa.String(length=64), nullable=True))
    op.add_column("organizations", sa.Column("agent_enrollment_token_created_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "agent_enrollment_token_created_at")
    op.drop_column("organizations", "agent_enrollment_token_hash")
