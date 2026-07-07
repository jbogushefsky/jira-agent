"""init jira_agent schema

Revision ID: 0001
Revises:
Create Date: 2026-07-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jira_agent"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("jira_key", sa.String(64), nullable=False, unique=True),
        sa.Column("jira_id", sa.String(64)),
        sa.Column("project_key", sa.String(64)),
        sa.Column("summary", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("raw_fields", postgresql.JSONB()),
        sa.Column("last_seen_status", sa.String(64), nullable=False),
        sa.Column("target_project_name", sa.String(255)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_tickets_jira_key", "tickets", ["jira_key"], schema=SCHEMA)

    op.create_table(
        "ticket_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(64)),
        sa.Column("to_status", sa.String(64), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("jira_changed_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_status_history_ticket_detected",
        "ticket_status_history",
        ["ticket_id", "detected_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "flows",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status_history_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.ticket_status_history.id"),
        ),
        sa.Column("transition_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("langsmith_run_id", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "transition_type IN ('to_in_progress','to_in_review','to_in_dev')",
            name="ck_flows_transition_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','partial')", name="ck_flows_status"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_flow_active",
        "flows",
        ["ticket_id", "transition_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','running')"),
        schema=SCHEMA,
    )

    op.create_table(
        "flow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "flow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.flows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_name", sa.String(128), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("input", postgresql.JSONB()),
        sa.Column("output", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','skipped')", name="ck_flow_steps_status"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flow_steps_flow_order", "flow_steps", ["flow_id", "step_order"], schema=SCHEMA
    )

    op.create_table(
        "test_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "flow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.flows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("acceptance_criterion", sa.Text()),
        sa.Column("scenario_title", sa.String(255), nullable=False),
        sa.Column("scenario_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "code_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "flow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.flows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_name", sa.String(255)),
        sa.Column("project_path", sa.String(512)),
        sa.Column("files_changed", postgresql.JSONB()),
        sa.Column("summary", sa.Text()),
        sa.Column("tests_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("code_changes", schema=SCHEMA)
    op.drop_table("test_scenarios", schema=SCHEMA)
    op.drop_table("flow_steps", schema=SCHEMA)
    op.drop_table("flows", schema=SCHEMA)
    op.drop_table("ticket_status_history", schema=SCHEMA)
    op.drop_table("tickets", schema=SCHEMA)
