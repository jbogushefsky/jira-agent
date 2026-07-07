from pathlib import Path

from app.graph.claude_cli import run_claude_code
from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState


@with_step_tracking("claude-code-generate-changes")
async def generate_code_changes(state: GraphState) -> dict:
    criteria = "\n".join(f"- {c}" for c in state.get("acceptance_criteria", [])) or "(none listed)"
    prompt = (
        f"Jira ticket {state['ticket_key']} moved to 'In Dev'. Implement the changes described below "
        f"in this repository.\n\n"
        f"Summary: {state.get('summary')}\n\n"
        f"Description:\n{state.get('description') or '(none)'}\n\n"
        f"Acceptance criteria:\n{criteria}\n\n"
        "Make the minimal set of code changes needed to satisfy every acceptance criterion. "
        "When you're done, summarize exactly what you changed and why."
    )

    project_path = Path(state["project_path"])
    result = await run_claude_code(
        prompt,
        cwd=project_path,
        allowed_tools="Read,Write,Edit,Bash,Glob,Grep",
        permission_mode="acceptEdits",
    )

    return {"code_change_summary": result.final_text, "claude_session_id": result.session_id}
