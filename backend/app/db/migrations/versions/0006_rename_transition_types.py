"""rename flows.transition_type values to match renamed Jira statuses

to_in_progress -> to_story_review, to_in_review -> to_generate_test_scenarios,
to_ai_resolve -> to_build_story, to_ambiguity_review -> to_requirement_review.
to_in_dev is unchanged.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jira_agent"

_RENAME_FORWARD = {
    "to_in_progress": "to_story_review",
    "to_in_review": "to_generate_test_scenarios",
    "to_ai_resolve": "to_build_story",
    "to_ambiguity_review": "to_requirement_review",
}
_RENAME_BACKWARD = {new: old for old, new in _RENAME_FORWARD.items()}


def upgrade() -> None:
    op.drop_constraint("ck_flows_transition_type", "flows", schema=SCHEMA, type_="check")
    for old, new in _RENAME_FORWARD.items():
        op.execute(
            text(f"UPDATE {SCHEMA}.flows SET transition_type = :new WHERE transition_type = :old").bindparams(
                new=new, old=old
            )
        )
    op.create_check_constraint(
        "ck_flows_transition_type",
        "flows",
        "transition_type IN ('to_story_review','to_generate_test_scenarios','to_in_dev','to_build_story','to_requirement_review')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("ck_flows_transition_type", "flows", schema=SCHEMA, type_="check")
    for new, old in _RENAME_BACKWARD.items():
        op.execute(
            text(f"UPDATE {SCHEMA}.flows SET transition_type = :old WHERE transition_type = :new").bindparams(
                old=old, new=new
            )
        )
    op.create_check_constraint(
        "ck_flows_transition_type",
        "flows",
        "transition_type IN ('to_in_progress','to_in_review','to_in_dev','to_ai_resolve','to_ambiguity_review')",
        schema=SCHEMA,
    )
