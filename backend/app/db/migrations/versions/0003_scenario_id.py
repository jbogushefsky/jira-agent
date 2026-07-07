"""add scenario_id to test_scenarios

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jira_agent"


def upgrade() -> None:
    op.add_column("test_scenarios", sa.Column("scenario_id", sa.String(32)), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("test_scenarios", "scenario_id", schema=SCHEMA)
