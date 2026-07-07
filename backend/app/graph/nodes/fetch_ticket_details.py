from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.mcp_jira.client import get_jira_client
from app.utils.ticket_parsing import extract_acceptance_criteria, extract_project_reference


@with_step_tracking("fetch-ticket-details")
async def fetch_ticket_details(state: GraphState) -> dict:
    jira = get_jira_client()
    issue = await jira.get_issue(state["ticket_key"])
    fields = issue.get("fields", issue)

    summary = fields.get("summary")
    description = fields.get("description")

    return {
        "ticket_fields": fields,
        "summary": summary,
        "description": description,
        "acceptance_criteria": extract_acceptance_criteria(fields, description),
        "project_name": extract_project_reference(summary, description),
    }
