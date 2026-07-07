"""Exposes this system's own processed-ticket data as an MCP server, so external MCP
clients (Claude Desktop, other agents) can query it — mounted at /mcp in app/main.py,
sharing the same FastAPI process/port as the REST API (see app/main.py's lifespan for
how the two coexist).
"""

import uuid

from mcp.server.fastmcp import FastMCP

from app.db import repository as repo
from app.db.session import session_scope

mcp = FastMCP("jira-agent-mcp")


@mcp.tool()
async def list_processed_tickets(status: str | None = None, limit: int = 50) -> list[dict]:
    """List Jira tickets that have had at least one agent flow run against them."""
    async with session_scope() as session:
        items, _total = await repo.list_processed_tickets(session, status=status, limit=limit)
        return [
            {**item, "lastProcessedAt": item["lastProcessedAt"].isoformat()} for item in items
        ]


@mcp.tool()
async def get_ticket_flow(ticket_key: str) -> list[dict]:
    """Get every agent flow run (AI - Story Review / AI - Generate Test Scenarios / In Dev) for a given ticket key."""
    async with session_scope() as session:
        flows = await repo.get_flows_for_ticket(session, ticket_key)
        return [
            {
                "flowId": str(flow.id),
                "transitionType": flow.transition_type,
                "status": flow.status,
                "startedAt": flow.started_at.isoformat() if flow.started_at else None,
                "completedAt": flow.completed_at.isoformat() if flow.completed_at else None,
                "errorMessage": flow.error_message,
            }
            for flow in flows
        ]


@mcp.tool()
async def get_flow_step_io(flow_id: str) -> list[dict]:
    """Get the ordered steps of a flow, including each step's exact input/output JSON."""
    async with session_scope() as session:
        steps = await repo.get_flow_steps(session, uuid.UUID(flow_id))
        return [
            {
                "stepId": str(step.id),
                "name": step.step_name,
                "order": step.step_order,
                "status": step.status,
                "input": step.input,
                "output": step.output,
                "error": step.error,
            }
            for step in steps
        ]


@mcp.tool()
async def get_ticket_status_history(ticket_key: str) -> list[dict]:
    """Get the full recorded status history for a ticket."""
    async with session_scope() as session:
        ticket = await repo.get_ticket_by_key(session, ticket_key)
        if ticket is None:
            return []
        history_rows = await repo.get_status_history(session, ticket.id)
        return [
            {
                "fromStatus": h.from_status,
                "toStatus": h.to_status,
                "detectedAt": h.detected_at.isoformat(),
            }
            for h in history_rows
        ]
