"""allow to_ai_resolve as a flows.transition_type

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jira_agent"


def upgrade() -> None:
    op.drop_constraint("ck_flows_transition_type", "flows", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_flows_transition_type",
        "flows",
        "transition_type IN ('to_in_progress','to_in_review','to_in_dev','to_ai_resolve')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("ck_flows_transition_type", "flows", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_flows_transition_type",
        "flows",
        "transition_type IN ('to_in_progress','to_in_review','to_in_dev')",
        schema=SCHEMA,
    )
