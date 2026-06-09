"""create system settings

Revision ID: 0005_create_system_settings
Revises: 0004_add_snmp_columns
Create Date: 2026-06-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_create_system_settings"
down_revision: Union[str, None] = "0004_add_snmp_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=120), primary_key=True, nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
