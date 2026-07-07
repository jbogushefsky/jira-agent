from pathlib import Path
from unittest.mock import AsyncMock

from app.graph.nodes import generate_code_changes as mod


async def test_generate_code_changes_invokes_claude_with_expected_prompt(monkeypatch, tmp_path):
    fake_result = type("R", (), {"final_text": "did the thing", "session_id": "sess-9"})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    state = {
        "ticket_key": "PROJ-1",
        "summary": "s",
        "description": "d",
        "acceptance_criteria": ["a", "b"],
        "project_path": str(tmp_path),
    }
    result = await mod.generate_code_changes.__wrapped__(state)

    assert result == {"code_change_summary": "did the thing", "claude_session_id": "sess-9"}
    run_claude.assert_awaited_once()
    _, kwargs = run_claude.call_args
    assert kwargs["cwd"] == Path(tmp_path)
    assert kwargs["permission_mode"] == "acceptEdits"
    assert kwargs["allowed_tools"] == "Read,Write,Edit,Bash,Glob,Grep"


async def test_generate_code_changes_handles_no_acceptance_criteria(monkeypatch, tmp_path):
    fake_result = type("R", (), {"final_text": "x", "session_id": None})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    state = {"ticket_key": "PROJ-1", "project_path": str(tmp_path)}
    result = await mod.generate_code_changes.__wrapped__(state)
    assert result["claude_session_id"] is None
