import asyncio
import uuid
from unittest.mock import AsyncMock

from app.graph.nodes import generate_tests as mod
from tests.helpers import make_fake_session_scope


async def test_generate_tests_resumes_session_when_available(monkeypatch, tmp_path):
    fake_result = type("R", (), {"final_text": "tests added", "session_id": "sess-1"})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    add_change = AsyncMock()
    monkeypatch.setattr(mod.repo, "add_code_change", add_change)
    monkeypatch.setattr(mod.repo, "get_test_scenarios_by_ticket", AsyncMock(return_value=[]))
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    state = {
        "ticket_key": "PROJ-1",
        "ticket_id": str(uuid.uuid4()),
        "project_path": str(tmp_path),
        "claude_session_id": "sess-1",
        "flow_id": str(uuid.uuid4()),
        "code_change_summary": "did stuff",
    }
    result = await mod.generate_tests.__wrapped__(state)

    assert result == {"test_generation_summary": "tests added"}
    _, kwargs = run_claude.call_args
    assert kwargs["resume_session_id"] == "sess-1"
    add_change.assert_awaited_once()


async def test_generate_tests_falls_back_to_git_diff_without_session(monkeypatch, tmp_path):
    fake_result = type("R", (), {"final_text": "tests from diff", "session_id": None})()
    run_claude = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(mod, "run_claude_code", run_claude)

    add_change = AsyncMock()
    monkeypatch.setattr(mod.repo, "add_code_change", add_change)
    monkeypatch.setattr(mod.repo, "get_test_scenarios_by_ticket", AsyncMock(return_value=[]))
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    class FakeProc:
        async def communicate(self):
            return b"diff --git a/file b/file\n+added line\n", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    state = {
        "ticket_key": "PROJ-1",
        "ticket_id": str(uuid.uuid4()),
        "project_path": str(tmp_path),
        "flow_id": str(uuid.uuid4()),
    }
    result = await mod.generate_tests.__wrapped__(state)

    assert result == {"test_generation_summary": "tests from diff"}
    _, kwargs = run_claude.call_args
    assert "resume_session_id" not in kwargs
    prompt_arg = run_claude.call_args.args[0]
    assert "diff --git" in prompt_arg
