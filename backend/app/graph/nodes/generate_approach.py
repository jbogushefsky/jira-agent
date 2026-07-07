from pathlib import Path
from tempfile import gettempdir

from app.graph.claude_cli import run_claude_code
from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.logging_config import get_logger
from app.utils.project_paths import ProjectNotFoundError, resolve_project_path

logger = get_logger(__name__)

_STORY_RUBRIC = (
    Path(__file__).resolve().parent.parent / "prompts" / "ai_resolve_story_rubric.md"
).read_text(encoding="utf-8")


@with_step_tracking("claude-code-generate-approach")
async def generate_approach(state: GraphState) -> dict:
    criteria = "\n".join(f"- {c}" for c in state.get("acceptance_criteria", [])) or "(none listed)"

    project_name = state.get("project_name")
    project_path: Path | None = None
    if project_name:
        try:
            project_path = resolve_project_path(project_name)
        except ProjectNotFoundError as exc:
            logger.warning("generate_approach_project_not_found", project_name=project_name, error=str(exc))

    if project_path is not None:
        cwd = project_path
        allowed_tools = "Read,Glob,Grep"
        project_context = (
            f"This ticket targets the '{project_name}' project, checked out at your current working "
            "directory. Explore the existing code (Read/Glob/Grep) as needed to ground the story in "
            "how the project actually works today. If a CLAUDE.md file exists here, follow its "
            "instructions too."
        )
    else:
        cwd = Path(gettempdir()) / "claude-runs" / state["flow_id"]
        cwd.mkdir(parents=True, exist_ok=True)
        allowed_tools = ""
        project_context = (
            "No target project was found for this ticket (no 'Project: <name>' reference) — "
            "work from the ticket text alone."
        )

    prompt = (
        f"Jira ticket {state['ticket_key']} was moved to 'AI - Build Story'. You are rewriting its "
        "description in place.\n\n"
        f"{project_context}\n\n"
        f"Current summary: {state.get('summary')}\n\n"
        f"Current description:\n{state.get('description') or '(none)'}\n\n"
        f"Current acceptance criteria:\n{criteria}\n\n"
        f"{_STORY_RUBRIC}\n\n"
        "Respond with ONLY the new ticket description, formatted as markdown, ready to paste "
        "directly into Jira as the ticket's full description — no preamble, no commentary about "
        "what you're doing."
    )

    result = await run_claude_code(prompt, cwd=cwd, allowed_tools=allowed_tools)

    return {"generated_description": result.final_text, "claude_session_id": result.session_id}
