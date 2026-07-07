import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import CodeChange, Flow, FlowStep, Ticket, TicketStatusHistory, TestScenario

settings = get_settings()


def _truncate(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    import json

    raw = json.dumps(payload, default=str)
    if len(raw.encode("utf-8")) <= settings.max_step_output_bytes:
        return payload
    return {
        "truncated": True,
        "preview": raw[: settings.max_step_output_bytes],
    }


# ---- Tickets -----------------------------------------------------------------


async def upsert_ticket(
    session: AsyncSession,
    *,
    jira_key: str,
    jira_id: str | None,
    project_key: str | None,
    summary: str | None,
    description: str | None,
    raw_fields: dict,
    status: str,
    target_project_name: str | None,
) -> Ticket:
    result = await session.execute(select(Ticket).where(Ticket.jira_key == jira_key))
    ticket = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if ticket is None:
        ticket = Ticket(
            jira_key=jira_key,
            jira_id=jira_id,
            project_key=project_key,
            summary=summary,
            description=description,
            raw_fields=raw_fields,
            last_seen_status=status,
            target_project_name=target_project_name,
            last_polled_at=now,
        )
        session.add(ticket)
    else:
        ticket.jira_id = jira_id
        ticket.project_key = project_key
        ticket.summary = summary
        ticket.description = description
        ticket.raw_fields = raw_fields
        ticket.target_project_name = target_project_name
        ticket.last_polled_at = now
        # Always sync to Jira's real current status, even when it's not one of the trigger
        # statuses — otherwise a ticket that passes through a non-trigger status (e.g. "To Do")
        # never updates our recorded baseline, and a later move back into a trigger status is
        # invisible to compute_transition() because previous_status is still stale.
        ticket.last_seen_status = status
    await session.flush()
    return ticket


async def record_status_change(
    session: AsyncSession, *, ticket: Ticket, from_status: str | None, to_status: str
) -> TicketStatusHistory:
    history = TicketStatusHistory(ticket_id=ticket.id, from_status=from_status, to_status=to_status)
    session.add(history)
    ticket.last_seen_status = to_status
    await session.flush()
    return history


async def get_ticket_by_key(session: AsyncSession, jira_key: str) -> Ticket | None:
    result = await session.execute(select(Ticket).where(Ticket.jira_key == jira_key))
    return result.scalar_one_or_none()


async def get_status_history(session: AsyncSession, ticket_id: uuid.UUID) -> list[TicketStatusHistory]:
    # Explicit query rather than lazy-loading ticket.status_history — accessing an unloaded
    # relationship attribute outside an active await raises sqlalchemy.exc.MissingGreenlet
    # under the async driver (confirmed live: this caused a 500 on GET /api/tickets/{key}).
    stmt = (
        select(TicketStatusHistory)
        .where(TicketStatusHistory.ticket_id == ticket_id)
        .order_by(TicketStatusHistory.detected_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_processed_tickets(
    session: AsyncSession,
    *,
    status: str | None = None,
    project: str | None = None,
    project_key: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """A ticket counts as 'processed' once it has at least one flow row.

    `project` filters on `target_project_name` (the sibling code repo a ticket's description points
    at, e.g. "dice-roll" — used by In Dev/AI - Build Story to pick a checkout). `project_key` filters on
    `project_key` (the actual Jira project the ticket lives in, e.g. "PROJ") — the two are unrelated
    concepts that happen to often share a value; the project-tabs UI filters by the latter.
    """
    base = select(Ticket).join(Flow, Flow.ticket_id == Ticket.id).distinct()
    if status:
        base = base.where(Ticket.last_seen_status == status)
    if project:
        base = base.where(Ticket.target_project_name == project)
    if project_key:
        base = base.where(Ticket.project_key == project_key)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = base.order_by(Ticket.last_polled_at.desc()).limit(limit).offset(offset)
    tickets = (await session.execute(stmt)).scalars().all()

    items = []
    for ticket in tickets:
        latest_flow = await get_latest_flow(session, ticket.id)
        items.append(
            {
                "key": ticket.jira_key,
                "title": ticket.summary,
                "jiraStatus": ticket.last_seen_status,
                "project": ticket.target_project_name,
                "projectKey": ticket.project_key,
                "lastProcessedAt": latest_flow.created_at if latest_flow else ticket.last_polled_at,
                "overallFlowStatus": latest_flow.status if latest_flow else "unknown",
                "latestFlowId": str(latest_flow.id) if latest_flow else None,
            }
        )
    return items, total


async def get_latest_flow(session: AsyncSession, ticket_id: uuid.UUID) -> Flow | None:
    stmt = (
        select(Flow)
        .where(Flow.ticket_id == ticket_id)
        .order_by(Flow.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---- Flows ---------------------------------------------------------------------


async def create_flow(
    session: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    status_history_id: uuid.UUID | None,
    transition_type: str,
) -> Flow:
    flow = Flow(
        ticket_id=ticket_id,
        status_history_id=status_history_id,
        transition_type=transition_type,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    session.add(flow)
    await session.flush()
    return flow


async def set_flow_status(
    session: AsyncSession,
    flow_id: uuid.UUID,
    *,
    status: str,
    error_message: str | None = None,
    langsmith_run_id: str | None = None,
) -> None:
    flow = await session.get(Flow, flow_id)
    if flow is None:
        return
    flow.status = status
    if error_message is not None:
        flow.error_message = error_message
    elif status == "running":
        # A replay moves a previously-failed flow back to "running" — clear the stale
        # error_message from that earlier attempt so the dashboard doesn't keep showing an
        # error on a flow that's actively running again.
        flow.error_message = None
    if langsmith_run_id is not None:
        flow.langsmith_run_id = langsmith_run_id
    if status in ("succeeded", "failed", "partial"):
        flow.completed_at = datetime.now(timezone.utc)
    elif status == "running":
        flow.completed_at = None
    await session.flush()


async def get_flows_for_ticket(session: AsyncSession, ticket_key: str) -> list[Flow]:
    stmt = (
        select(Flow)
        .join(Ticket, Flow.ticket_id == Ticket.id)
        .where(Ticket.jira_key == ticket_key)
        .order_by(Flow.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_flow(session: AsyncSession, flow_id: uuid.UUID) -> Flow | None:
    return await session.get(Flow, flow_id)


# ---- Flow steps ------------------------------------------------------------------


async def start_flow_step(
    session: AsyncSession, *, flow_id: uuid.UUID, step_name: str, step_order: int, input_payload: dict
) -> FlowStep:
    step = FlowStep(
        flow_id=flow_id,
        step_name=step_name,
        step_order=step_order,
        status="running",
        input=_truncate(input_payload),
    )
    session.add(step)
    await session.flush()
    return step


async def finish_flow_step(
    session: AsyncSession,
    step_id: uuid.UUID,
    *,
    status: str,
    output: dict | None = None,
    error: str | None = None,
) -> FlowStep | None:
    step = await session.get(FlowStep, step_id)
    if step is None:
        return None
    step.status = status
    step.output = _truncate(output)
    step.error = error
    now = datetime.now(timezone.utc)
    step.completed_at = now
    started = step.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    step.duration_ms = int((now - started).total_seconds() * 1000)
    await session.flush()
    return step


async def get_flow_steps(session: AsyncSession, flow_id: uuid.UUID) -> list[FlowStep]:
    # Secondary sort by started_at: step_order has no uniqueness constraint, so a replayed step
    # (run_replay deliberately restarts its own numbering from the current step count, but this
    # guards against any future path that doesn't) sorts after the attempt it repeats rather
    # than in an arbitrary tie order.
    stmt = (
        select(FlowStep)
        .where(FlowStep.flow_id == flow_id)
        .order_by(FlowStep.step_order, FlowStep.started_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_step(session: AsyncSession, step_id: uuid.UUID) -> FlowStep | None:
    return await session.get(FlowStep, step_id)


# ---- Test scenarios / code changes -----------------------------------------------


async def add_test_scenario(
    session: AsyncSession,
    *,
    flow_id: uuid.UUID,
    ticket_id: uuid.UUID,
    scenario_id: str | None,
    acceptance_criterion: str | None,
    scenario_title: str,
    scenario_body: str,
) -> TestScenario:
    scenario = TestScenario(
        flow_id=flow_id,
        ticket_id=ticket_id,
        scenario_id=scenario_id,
        acceptance_criterion=acceptance_criterion,
        scenario_title=scenario_title,
        scenario_body=scenario_body,
    )
    session.add(scenario)
    await session.flush()
    return scenario


async def get_test_scenarios_by_ticket(session: AsyncSession, ticket_id: uuid.UUID) -> list[TestScenario]:
    stmt = (
        select(TestScenario)
        .where(TestScenario.ticket_id == ticket_id)
        .order_by(TestScenario.scenario_id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_code_change(
    session: AsyncSession,
    *,
    flow_id: uuid.UUID,
    project_name: str | None,
    project_path: str | None,
    files_changed: dict | None,
    summary: str | None,
    tests_summary: str | None,
) -> CodeChange:
    change = CodeChange(
        flow_id=flow_id,
        project_name=project_name,
        project_path=project_path,
        files_changed=files_changed,
        summary=summary,
        tests_summary=tests_summary,
    )
    session.add(change)
    await session.flush()
    return change
