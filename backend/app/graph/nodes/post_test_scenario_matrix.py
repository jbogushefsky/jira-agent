from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.mcp_jira.client import get_jira_client


def _escape_cell(text: str) -> str:
    # Markdown table cells can't contain raw newlines or unescaped pipes.
    return text.replace("|", "\\|").replace("\n", "<br>")


def _build_matrix(scenarios: list[dict]) -> str:
    header = "| ID | Acceptance Criterion | Scenario | Given/When/Then |"
    separator = "|----|----------------------|----------|------------------|"
    rows = [
        "| {id} | {ac} | {title} | {body} |".format(
            id=_escape_cell(s.get("scenario_id") or "(unassigned)"),
            ac=_escape_cell(s.get("acceptance_criterion") or "(none)"),
            title=_escape_cell(s.get("title") or "(untitled)"),
            body=_escape_cell(s.get("body") or ""),
        )
        for s in scenarios
    ]
    return "\n".join([header, separator, *rows])


@with_step_tracking("post-test-scenario-matrix-to-jira")
async def post_test_scenario_matrix(state: GraphState) -> dict:
    scenarios = state.get("test_scenarios", [])
    if not scenarios:
        return {}

    existing_description = state.get("description") or ""
    matrix = _build_matrix(scenarios)
    new_description = f"{existing_description}\n\n## Test Scenario Traceability Matrix\n\n{matrix}"

    jira = get_jira_client()
    await jira.update_description(state["ticket_key"], new_description)
    return {}
