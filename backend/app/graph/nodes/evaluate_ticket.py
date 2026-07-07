from pathlib import Path
from tempfile import gettempdir

from app.graph.claude_cli import run_claude_code
from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.logging_config import get_logger
from app.utils.project_paths import ProjectNotFoundError, resolve_project_path

logger = get_logger(__name__)


@with_step_tracking("claude-code-evaluate")
async def evaluate_ticket(state: GraphState) -> dict:
    criteria = "\n".join(f"- {c}" for c in state.get("acceptance_criteria", [])) or "(none listed)"

    project_name = state.get("project_name")
    project_path: Path | None = None
    if project_name:
        try:
            project_path = resolve_project_path(project_name)
        except ProjectNotFoundError as exc:
            logger.warning("evaluate_ticket_project_not_found", project_name=project_name, error=str(exc))

    if project_path is not None:
        cwd = project_path
        allowed_tools = "Read,Glob,Grep"
        project_context = (
            f"This ticket targets the '{project_name}' project, checked out at your current working "
            "directory. Explore the existing code (Read/Glob/Grep) as needed to ground your evaluation "
            "in how the project actually works today. If a CLAUDE.md file exists here, follow its "
            "instructions for how this project wants tickets evaluated."
        )
    else:
        cwd = Path(gettempdir()) / "claude-runs" / state["flow_id"]
        cwd.mkdir(parents=True, exist_ok=True)
        allowed_tools = ""
        project_context = (
            "No target project was found for this ticket (no 'Project: <name>' reference) — "
            "evaluate it on the ticket text alone."
        )

    prompt = (
        f"You are reviewing Jira ticket {state['ticket_key']} which just moved to 'AI - Story Review'.\n\n"
        f"{project_context}\n\n"
        f"Summary: {state.get('summary')}\n\n"
        f"Description:\n{state.get('description') or '(none)'}\n\n"
        f"Acceptance criteria:\n{criteria}\n\n"
        "Evaluate the ticket for clarity, scope risk, missing edge cases, and technical approach. "
        "Provide concrete, actionable recommendations for the engineer picking this up. "
        "Respond with the recommendations only, formatted as concise markdown."
    )

    result = await run_claude_code(prompt, cwd=cwd, allowed_tools=allowed_tools)

    return {
        "recommendations": result.final_text,
        "claude_session_id": result.session_id,
        "project_path": str(project_path) if project_path else None,
    }
