"""add department cost center

Revision ID: 0019_department_cost_center
Revises: 0018_add_agent_local_admin
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_department_cost_center"
down_revision: Union[str, None] = "0018_add_agent_local_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("cost_center", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("departments", "cost_center")
