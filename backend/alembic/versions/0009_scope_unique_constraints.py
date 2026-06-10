"""scope unique constraints by organization

Revision ID: 0009_org_unique_constraints
Revises: 0008_organizations
Create Date: 2026-06-09 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009_org_unique_constraints"
down_revision: Union[str, None] = "0008_organizations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("departments_name_key", "departments", type_="unique")
    op.drop_constraint("printers_name_key", "printers", type_="unique")
    op.drop_constraint("users_username_key", "users", type_="unique")
    op.drop_constraint("print_agents_agent_uid_key", "print_agents", type_="unique")

    op.create_unique_constraint("uq_departments_org_name", "departments", ["organization_id", "name"])
    op.create_unique_constraint("uq_printers_org_name", "printers", ["organization_id", "name"])
    op.create_unique_constraint("uq_users_org_username", "users", ["organization_id", "username"])
    op.create_unique_constraint("uq_print_agents_org_uid", "print_agents", ["organization_id", "agent_uid"])


def downgrade() -> None:
    op.drop_constraint("uq_print_agents_org_uid", "print_agents", type_="unique")
    op.drop_constraint("uq_users_org_username", "users", type_="unique")
    op.drop_constraint("uq_printers_org_name", "printers", type_="unique")
    op.drop_constraint("uq_departments_org_name", "departments", type_="unique")

    op.create_unique_constraint("print_agents_agent_uid_key", "print_agents", ["agent_uid"])
    op.create_unique_constraint("users_username_key", "users", ["username"])
    op.create_unique_constraint("printers_name_key", "printers", ["name"])
    op.create_unique_constraint("departments_name_key", "departments", ["name"])
