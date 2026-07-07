from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.mcp_jira.client import get_jira_client


def _build_questions_section(questions: list[dict]) -> str:
    lines = [
        "## Clarification Questions (AI - Requirement Review)",
        "",
        "The following requirements were flagged as ambiguous. Please answer each question directly "
        "below it.",
        "",
    ]
    for i, q in enumerate(questions, start=1):
        lines.append(f"{i}. **Requirement:** {q.get('requirement') or '(unspecified)'}")
        lines.append(f"   **Question:** {q.get('question') or '(unspecified)'}")
        lines.append("   **Answer:** _(pending)_")
        lines.append("")
    return "\n".join(lines).rstrip()


@with_step_tracking("post-ambiguity-questions-to-jira")
async def post_ambiguity_questions(state: GraphState) -> dict:
    questions = state.get("ambiguity_questions") or []
    if not questions:
        return {}

    existing_description = state.get("description") or ""
    section = _build_questions_section(questions)
    new_description = f"{existing_description}\n\n{section}"

    jira = get_jira_client()
    await jira.update_description(state["ticket_key"], new_description)
    return {}
