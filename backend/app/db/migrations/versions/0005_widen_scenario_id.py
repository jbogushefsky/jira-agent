"""widen test_scenarios.scenario_id for {ticket}-AC-##-TC-## format

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jira_agent"


def upgrade() -> None:
    op.alter_column(
        "test_scenarios",
        "scenario_id",
        existing_type=sa.String(32),
        type_=sa.String(64),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        "test_scenarios",
        "scenario_id",
        existing_type=sa.String(64),
        type_=sa.String(32),
        schema=SCHEMA,
    )
