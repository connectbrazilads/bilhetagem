"""add cost and balance

Revision ID: 0002_add_cost_and_balance
Revises: 0001_initial_schema
Create Date: 2026-06-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_cost_and_balance"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to printers
    op.add_column("printers", sa.Column("cost_mono", sa.Float(), nullable=False, server_default="0.05"))
    op.add_column("printers", sa.Column("cost_color", sa.Float(), nullable=False, server_default="0.25"))

    # Add columns to quotas
    op.add_column("quotas", sa.Column("monthly_balance", sa.Float(), nullable=False, server_default="50.0"))
    op.add_column("quotas", sa.Column("used_balance", sa.Float(), nullable=False, server_default="0.0"))

    # Add columns to print_jobs
    op.add_column("print_jobs", sa.Column("cost", sa.Float(), nullable=False, server_default="0.0"))


def downgrade() -> None:
    op.drop_column("print_jobs", "cost")
    op.drop_column("quotas", "used_balance")
    op.drop_column("quotas", "monthly_balance")
    op.drop_column("printers", "cost_color")
    op.drop_column("printers", "cost_mono")
