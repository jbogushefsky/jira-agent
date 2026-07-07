from unittest.mock import AsyncMock

from app.graph.nodes import generate_approach as mod
from app.utils.project_paths import ProjectNotFoundError


async def test_generate_approach_with_project(monkeypatch, tmp_path):
    project_dir = tmp_path / "dice-roll"
    project_dir.mkdir()
    monkeypatch.setattr(mod, "resolve_project_path", lambda name: project_dir)

    fake_result = type("R", (), {"final_text": "Project: dice-roll\n\n## User Story\n...", "session_id": "sess-5"})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    state = {
        "ticket_key": "PROJ-1",
        "project_name": "dice-roll",
        "summary": "s",
        "description": "d",
        "acceptance_criteria": ["a"],
        "flow_id": "flow-1",
    }
    result = await mod.generate_approach.__wrapped__(state)

    assert result["generated_description"].startswith("Project: dice-roll")
    assert result["claude_session_id"] == "sess-5"
    _, kwargs = run_claude.call_args
    assert kwargs["cwd"] == project_dir
    assert kwargs["allowed_tools"] == "Read,Glob,Grep"
    prompt = run_claude.call_args.args[0]
    assert "AI - Build Story" in prompt
    assert "Project reference line" in prompt  # confirms the rubric file got inlined


async def test_generate_approach_falls_back_without_project(monkeypatch, tmp_path):
    def raise_not_found(name):
        raise ProjectNotFoundError("nope")

    monkeypatch.setattr(mod, "resolve_project_path", raise_not_found)
    monkeypatch.setattr(mod, "gettempdir", lambda: str(tmp_path))

    fake_result = type("R", (), {"final_text": "some story", "session_id": None})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    state = {"ticket_key": "PROJ-2", "project_name": "missing", "flow_id": "flow-2"}
    result = await mod.generate_approach.__wrapped__(state)

    assert result["generated_description"] == "some story"
    _, kwargs = run_claude.call_args
    assert kwargs["allowed_tools"] == ""
