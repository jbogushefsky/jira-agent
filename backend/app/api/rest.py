import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ConfigResponse,
    FlowStepDetail,
    FlowStepSummary,
    FlowSummary,
    GraphDefinitionResponse,
    ReplayResponse,
    StatusHistoryEntry,
    TicketDetailResponse,
    TicketListResponse,
)
from app.config import get_settings
from app.db import repository as repo
from app.db.session import get_session
from app.graph.graph import NODE_STEP_NAMES, get_mermaid_definition, run_replay

router = APIRouter()
settings = get_settings()


def _langsmith_trace_url(run_id: str | None) -> str | None:
    if not run_id:
        return None
    return f"https://smith.langchain.com/o/-/projects/p/{settings.langchain_project}/r/{run_id}"


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict:
    from sqlalchemy import text

    await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    return ConfigResponse(
        jiraBaseUrl=settings.jira_url,
        langsmithBaseUrl="https://smith.langchain.com",
        triggerStatuses=list(settings.trigger_statuses.keys()),
        pollIntervalSeconds=settings.poll_interval_seconds,
        jiraProjectKeys=settings.jira_project_key_list,
    )


@router.get("/graph", response_model=GraphDefinitionResponse)
async def get_graph_definition() -> GraphDefinitionResponse:
    """The LangGraph flow's actual wiring, as Mermaid source, plus which `flow_steps.step_name`
    each node corresponds to — lets the frontend highlight a flow's executed nodes without
    hand-maintaining a duplicate diagram or name mapping.
    """
    return GraphDefinitionResponse(mermaid=get_mermaid_definition(), nodeStepNames=NODE_STEP_NAMES)


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    status: str | None = None,
    project: str | None = None,
    projectKey: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> TicketListResponse:
    items, total = await repo.list_processed_tickets(
        session, status=status, project=project, project_key=projectKey, limit=limit, offset=offset
    )
    return TicketListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/tickets/{ticket_key}", response_model=TicketDetailResponse)
async def get_ticket_detail(
    ticket_key: str, session: AsyncSession = Depends(get_session)
) -> TicketDetailResponse:
    ticket = await repo.get_ticket_by_key(session, ticket_key)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    history_rows = await repo.get_status_history(session, ticket.id)
    history = [
        StatusHistoryEntry(fromStatus=h.from_status, toStatus=h.to_status, detectedAt=h.detected_at)
        for h in history_rows
    ]
    return TicketDetailResponse(
        key=ticket.jira_key,
        title=ticket.summary,
        jiraStatus=ticket.last_seen_status,
        project=ticket.target_project_name,
        jiraUrl=f"{settings.jira_url.rstrip('/')}/browse/{ticket.jira_key}",
        statusHistory=history,
    )


_TRANSITION_LABELS = {v: k for k, v in settings.trigger_statuses.items()}


@router.get("/tickets/{ticket_key}/flows", response_model=list[FlowSummary])
async def get_ticket_flows(
    ticket_key: str, session: AsyncSession = Depends(get_session)
) -> list[FlowSummary]:
    flows = await repo.get_flows_for_ticket(session, ticket_key)
    result = []
    for flow in flows:
        steps = await repo.get_flow_steps(session, flow.id)
        result.append(
            FlowSummary(
                flowId=str(flow.id),
                triggerStatus=_TRANSITION_LABELS.get(flow.transition_type, flow.transition_type),
                startedAt=flow.started_at,
                finishedAt=flow.completed_at,
                status=flow.status,
                stepCount=len(steps),
            )
        )
    return result


@router.get("/flows/{flow_id}", response_model=FlowSummary)
async def get_flow(flow_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> FlowSummary:
    flow = await repo.get_flow(session, flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="flow not found")
    steps = await repo.get_flow_steps(session, flow.id)
    return FlowSummary(
        flowId=str(flow.id),
        triggerStatus=_TRANSITION_LABELS.get(flow.transition_type, flow.transition_type),
        startedAt=flow.started_at,
        finishedAt=flow.completed_at,
        status=flow.status,
        stepCount=len(steps),
    )


@router.get("/flows/{flow_id}/steps", response_model=list[FlowStepSummary])
async def get_flow_steps(
    flow_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[FlowStepSummary]:
    steps = await repo.get_flow_steps(session, flow_id)
    return [
        FlowStepSummary(
            id=str(s.id),
            name=s.step_name,
            order=s.step_order,
            status=s.status,
            startedAt=s.started_at,
            finishedAt=s.completed_at,
            durationMs=s.duration_ms,
        )
        for s in steps
    ]


@router.get("/steps/{step_id}", response_model=FlowStepDetail)
async def get_step_detail(
    step_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FlowStepDetail:
    step = await repo.get_step(session, step_id)
    if step is None:
        raise HTTPException(status_code=404, detail="step not found")
    flow = await repo.get_flow(session, step.flow_id)
    return FlowStepDetail(
        id=str(step.id),
        flowId=str(step.flow_id),
        name=step.step_name,
        status=step.status,
        startedAt=step.started_at,
        finishedAt=step.completed_at,
        input=step.input,
        output=step.output,
        error=step.error,
        langsmithTraceUrl=_langsmith_trace_url(flow.langsmith_run_id if flow else None),
    )


@router.post("/steps/{step_id}/replay", response_model=ReplayResponse, status_code=202)
async def replay_step(
    step_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ReplayResponse:
    step = await repo.get_step(session, step_id)
    if step is None:
        raise HTTPException(status_code=404, detail="step not found")
    if step.status != "failed":
        raise HTTPException(status_code=400, detail="only failed steps can be replayed")
    # Decoupled from the request the same way run_flow is decoupled from the poll tick — the
    # replay can take as long as a full Claude Code invocation, well past any reasonable HTTP
    # timeout, so the client polls the usual flow/step endpoints for progress instead.
    asyncio.create_task(
        run_replay(flow_id=step.flow_id, step_name=step.step_name, step_input=step.input or {})
    )
    return ReplayResponse(status="replay_started")
