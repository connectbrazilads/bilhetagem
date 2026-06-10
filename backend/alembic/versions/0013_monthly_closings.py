"""add monthly closings

Revision ID: 0013_monthly_closings
Revises: 0012_print_policies
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_monthly_closings"
down_revision: Union[str, None] = "0012_print_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monthly_closings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("total_jobs", sa.Integer(), nullable=False),
        sa.Column("billable_jobs", sa.Integer(), nullable=False),
        sa.Column("pending_jobs", sa.Integer(), nullable=False),
        sa.Column("blocked_jobs", sa.Integer(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("mono_pages", sa.Integer(), nullable=False),
        sa.Column("color_pages", sa.Integer(), nullable=False),
        sa.Column("blocked_pages", sa.Integer(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "year", "month", name="uq_monthly_closings_org_period"),
    )


def downgrade() -> None:
    op.drop_table("monthly_closings")
