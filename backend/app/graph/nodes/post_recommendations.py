from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.mcp_jira.client import get_jira_client


@with_step_tracking("post-recommendations-to-jira")
async def post_recommendations(state: GraphState) -> dict:
    jira = get_jira_client()
    recommendations = state.get("recommendations") or "(no recommendations generated)"
    comment = f"**Automated review recommendations**\n\n{recommendations}"
    await jira.add_comment(state["ticket_key"], comment)
    return {}
