"""add organization billing fields

Revision ID: 0017_organization_billing_fields
Revises: 0016_restore_queue_action
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_organization_billing_fields"
down_revision: Union[str, None] = "0016_restore_queue_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("billing_plan", sa.String(length=40), nullable=False, server_default="starter"))
    op.add_column("organizations", sa.Column("billing_status", sa.String(length=40), nullable=False, server_default="trial"))
    op.add_column("organizations", sa.Column("contracted_printer_limit", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("organizations", "contracted_printer_limit")
    op.drop_column("organizations", "billing_status")
    op.drop_column("organizations", "billing_plan")
