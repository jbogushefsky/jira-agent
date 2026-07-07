import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    jira_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    jira_id: Mapped[str | None] = mapped_column(String(64))
    project_key: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    raw_fields: Mapped[dict | None] = mapped_column(JSONB)
    last_seen_status: Mapped[str] = mapped_column(String(64), nullable=False)
    target_project_name: Mapped[str | None] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_polled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    status_history: Mapped[list["TicketStatusHistory"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    flows: Mapped[list["Flow"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"
    __table_args__ = (Index("ix_status_history_ticket_detected", "ticket_id", "detected_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jira_agent.tickets.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(64))
    to_status: Mapped[str] = mapped_column(String(64), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    jira_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticket: Mapped["Ticket"] = relationship(back_populates="status_history")


class Flow(Base):
    __tablename__ = "flows"
    __table_args__ = (
        CheckConstraint(
            "transition_type IN ('to_story_review','to_generate_test_scenarios','to_in_dev','to_build_story','to_requirement_review')",
            name="ck_flows_transition_type",
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','partial')",
            name="ck_flows_status",
        ),
        Index(
            "uq_flow_active",
            "ticket_id",
            "transition_type",
            unique=True,
            postgresql_where=text("status IN ('pending','running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jira_agent.tickets.id", ondelete="CASCADE"), nullable=False
    )
    status_history_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jira_agent.ticket_status_history.id")
    )
    transition_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    langsmith_run_id: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["Ticket"] = relationship(back_populates="flows")
    steps: Mapped[list["FlowStep"]] = relationship(
        back_populates="flow", cascade="all, delete-orphan", order_by="FlowStep.step_order"
    )


class FlowStep(Base):
    __tablename__ = "flow_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','succeeded','failed','skipped')", name="ck_flow_steps_status"
        ),
        Index("ix_flow_steps_flow_order", "flow_id", "step_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jira_agent.flows.id", ondelete="CASCADE"), nullable=False
    )
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="running")
    input: Mapped[dict | None] = mapped_column(JSONB)
    output: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    flow: Mapped["Flow"] = relationship(back_populates="steps")


class TestScenario(Base):
    __tablename__ = "test_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jira_agent.flows.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jira_agent.tickets.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[str | None] = mapped_column(String(64))
    acceptance_criterion: Mapped[str | None] = mapped_column(Text)
    scenario_title: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CodeChange(Base):
    __tablename__ = "code_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jira_agent.flows.id", ondelete="CASCADE"), nullable=False
    )
    project_name: Mapped[str | None] = mapped_column(String(255))
    project_path: Mapped[str | None] = mapped_column(String(512))
    files_changed: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    tests_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
