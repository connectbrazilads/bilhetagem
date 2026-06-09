"""add release statuses

Revision ID: 0003_add_release_statuses
Revises: 0002_add_cost_and_balance
Create Date: 2026-06-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_release_statuses"
down_revision: Union[str, None] = "0002_add_cost_and_balance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Exit transaction block to run ALTER TYPE
    op.execute("COMMIT")
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'pending_release'")
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'released'")
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    pass
