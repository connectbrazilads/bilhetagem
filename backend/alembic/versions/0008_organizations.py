"""add organizations foundation

Revision ID: 0008_organizations
Revises: 0007_agent_printer_aliases
Create Date: 2026-06-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_organizations"
down_revision: Union[str, None] = "0007_agent_printer_aliases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORG_TABLES = (
    "departments",
    "printers",
    "users",
    "quotas",
    "print_jobs",
    "audit_logs",
    "print_agents",
    "printer_aliases",
)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.execute("INSERT INTO organizations (id, name, slug, is_active) VALUES (1, 'Empresa Padrao', 'default', true)")

    for table_name in ORG_TABLES:
        op.add_column(table_name, sa.Column("organization_id", sa.Integer(), nullable=True))
        op.execute(f"UPDATE {table_name} SET organization_id = 1")
        op.alter_column(table_name, "organization_id", nullable=False)
        op.create_foreign_key(f"fk_{table_name}_organization_id", table_name, "organizations", ["organization_id"], ["id"])

    op.add_column("system_settings", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.execute("UPDATE system_settings SET organization_id = 1")
    op.alter_column("system_settings", "organization_id", nullable=False)
    op.drop_constraint("system_settings_pkey", "system_settings", type_="primary")
    op.create_primary_key("pk_system_settings", "system_settings", ["organization_id", "key"])
    op.create_foreign_key("fk_system_settings_organization_id", "system_settings", "organizations", ["organization_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_system_settings_organization_id", "system_settings", type_="foreignkey")
    op.drop_constraint("pk_system_settings", "system_settings", type_="primary")
    op.create_primary_key("system_settings_pkey", "system_settings", ["key"])
    op.drop_column("system_settings", "organization_id")

    for table_name in reversed(ORG_TABLES):
        op.drop_constraint(f"fk_{table_name}_organization_id", table_name, type_="foreignkey")
        op.drop_column(table_name, "organization_id")

    op.drop_table("organizations")
