from unittest.mock import AsyncMock

from app.graph.nodes import evaluate_ticket as mod
from app.utils.project_paths import ProjectNotFoundError


async def test_evaluate_ticket_with_resolved_project(monkeypatch, tmp_path):
    project_dir = tmp_path / "dice-roll"
    project_dir.mkdir()
    monkeypatch.setattr(mod, "resolve_project_path", lambda name: project_dir)

    fake_result = type("R", (), {"final_text": "recommendations text", "session_id": "sess-1"})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    state = {
        "ticket_key": "PROJ-1",
        "project_name": "dice-roll",
        "summary": "s",
        "description": "d",
        "acceptance_criteria": ["a"],
    }
    result = await mod.evaluate_ticket.__wrapped__(state)

    assert result["recommendations"] == "recommendations text"
    assert result["project_path"] == str(project_dir)
    run_claude.assert_awaited_once()
    _, kwargs = run_claude.call_args
    assert kwargs["cwd"] == project_dir
    assert kwargs["allowed_tools"] == "Read,Glob,Grep"


async def test_evaluate_ticket_falls_back_when_project_not_found(monkeypatch, tmp_path):
    def raise_not_found(name):
        raise ProjectNotFoundError("nope")

    monkeypatch.setattr(mod, "resolve_project_path", raise_not_found)
    monkeypatch.setattr(mod, "gettempdir", lambda: str(tmp_path))

    fake_result = type("R", (), {"final_text": "no project recs", "session_id": None})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    state = {"ticket_key": "PROJ-2", "project_name": "unknown-project", "flow_id": "flow-1"}
    result = await mod.evaluate_ticket.__wrapped__(state)

    assert result["recommendations"] == "no project recs"
    assert result["project_path"] is None
    _, kwargs = run_claude.call_args
    assert kwargs["allowed_tools"] == ""


async def test_evaluate_ticket_no_project_name_at_all(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "gettempdir", lambda: str(tmp_path))
    fake_result = type("R", (), {"final_text": "text", "session_id": None})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    state = {"ticket_key": "PROJ-3", "flow_id": "flow-2"}
    result = await mod.evaluate_ticket.__wrapped__(state)
    assert result["project_path"] is None
