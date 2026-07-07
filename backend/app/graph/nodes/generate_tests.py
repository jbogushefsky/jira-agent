import uuid
from pathlib import Path

from app.db import repository as repo
from app.db.session import session_scope
from app.graph.claude_cli import run_claude_code
from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState


@with_step_tracking("claude-code-generate-tests")
async def generate_tests(state: GraphState) -> dict:
    project_path = Path(state["project_path"])
    session_id = state.get("claude_session_id")

    async with session_scope() as db_session:
        scenarios = await repo.get_test_scenarios_by_ticket(db_session, uuid.UUID(state["ticket_id"]))

    if scenarios:
        scenario_list = "\n".join(
            f"- {s.scenario_id}: {s.scenario_title}" for s in scenarios if s.scenario_id
        )
        traceability_instruction = (
            "\n\nThis ticket has the following Test Scenario traceability IDs on record:\n"
            f"{scenario_list}\n\n"
            "Every test you write must reference the specific Test Scenario traceability ID it "
            "implements in that test's comment or docstring (e.g. `# PROJ-42-AC-01-TC-01` or a "
            "docstring line naming the id). If a test doesn't correspond to any listed scenario, "
            "note that in your summary instead of inventing an id."
        )
    else:
        traceability_instruction = ""

    base_prompt = (
        f"Write automated tests covering the code changes just made for Jira ticket "
        f"{state['ticket_key']} in this repository. Use the project's existing test framework and "
        f"conventions. Summarize which tests you added and what they cover.{traceability_instruction}"
    )

    if session_id:
        prompt = base_prompt
        result = await run_claude_code(
            prompt,
            cwd=project_path,
            allowed_tools="Read,Write,Edit,Bash,Glob,Grep",
            permission_mode="acceptEdits",
            resume_session_id=session_id,
        )
    else:
        # Session resume wasn't available (e.g. prior step produced no session id) — fall back to
        # giving the model the actual diff as context instead of relying on conversation memory.
        diff = await _git_diff(project_path)
        prompt = (
            f"{base_prompt}\n\nHere is the diff of the changes already made:\n```diff\n{diff}\n```"
        )
        result = await run_claude_code(
            prompt,
            cwd=project_path,
            allowed_tools="Read,Write,Edit,Bash,Glob,Grep",
            permission_mode="acceptEdits",
        )

    async with session_scope() as db_session:
        await repo.add_code_change(
            db_session,
            flow_id=uuid.UUID(state["flow_id"]),
            project_name=state.get("project_name"),
            project_path=str(project_path),
            files_changed=None,
            summary=state.get("code_change_summary"),
            tests_summary=result.final_text,
        )

    return {"test_generation_summary": result.final_text}


async def _git_diff(project_path: Path) -> str:
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "git",
        "diff",
        cwd=str(project_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="replace")[:20_000]
