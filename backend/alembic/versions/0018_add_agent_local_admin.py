"""add agent local admin flag

Revision ID: 0018_add_agent_local_admin
Revises: 0017_organization_billing_fields
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018_add_agent_local_admin"
down_revision: Union[str, None] = "0017_organization_billing_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("print_agents", sa.Column("local_admin", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("print_agents", "local_admin")
