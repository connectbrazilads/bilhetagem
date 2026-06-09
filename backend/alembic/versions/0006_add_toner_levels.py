"""add toner levels

Revision ID: 0006_add_toner_levels
Revises: 0005_create_system_settings
Create Date: 2026-06-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_toner_levels"
down_revision: Union[str, None] = "0005_create_system_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("printers", sa.Column("toner_levels", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("printers", "toner_levels")
