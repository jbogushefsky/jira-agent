from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.mcp_jira.client import get_jira_client


@with_step_tracking("update-ticket-description")
async def update_ticket_description(state: GraphState) -> dict:
    jira = get_jira_client()
    description = state.get("generated_description") or "(no description generated)"
    await jira.update_description(state["ticket_key"], description)
    return {}
