"""add snmp columns

Revision ID: 0004_add_snmp_columns
Revises: 0003_add_release_statuses
Create Date: 2026-06-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_snmp_columns"
down_revision: Union[str, None] = "0003_add_release_statuses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("printers", sa.Column("ip_address", sa.String(length=45), nullable=True))
    op.add_column("printers", sa.Column("toner_level", sa.Integer(), nullable=True))
    op.add_column("printers", sa.Column("paper_status", sa.String(length=50), nullable=True))
    op.add_column("printers", sa.Column("serial_number", sa.String(length=80), nullable=True))
    op.add_column("printers", sa.Column("page_counter", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("printers", "page_counter")
    op.drop_column("printers", "serial_number")
    op.drop_column("printers", "paper_status")
    op.drop_column("printers", "toner_level")
    op.drop_column("printers", "ip_address")
