import asyncio
import json

import pytest

from app.graph import claude_cli
from app.graph.claude_cli import (
    ClaudeCliError,
    ClaudeCliTimeoutError,
    _kill_process_group,
    _summarize_events,
    run_claude_code,
)


class FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int, pid: int = 1234):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = pid

    async def communicate(self):
        return self._stdout, self._stderr


def _lines(*events: dict) -> bytes:
    return ("\n".join(json.dumps(e) for e in events) + "\n").encode()


async def test_run_claude_code_success(monkeypatch, tmp_path):
    stdout = _lines(
        {"type": "system", "subtype": "init", "session_id": "sess-1"},
        {"type": "result", "result": "done", "is_error": False, "duration_ms": 10, "total_cost_usd": 0.01},
    )

    async def fake_exec(*args, **kwargs):
        return FakeProcess(stdout, b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await run_claude_code("prompt text", cwd=tmp_path, allowed_tools="Read")

    assert result.session_id == "sess-1"
    assert result.final_text == "done"
    assert result.is_error is False
    assert result.duration_ms == 10
    assert result.total_cost_usd == 0.01


async def test_run_claude_code_uses_assistant_text_when_no_result_event(monkeypatch, tmp_path):
    stdout = _lines(
        {"type": "system", "subtype": "init", "session_id": "sess-2"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "partial answer"}]}},
    )

    async def fake_exec(*args, **kwargs):
        return FakeProcess(stdout, b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await run_claude_code("prompt", cwd=tmp_path)
    assert result.final_text == "partial answer"


async def test_run_claude_code_passes_through_resume_and_extra_dirs(monkeypatch, tmp_path):
    stdout = _lines({"type": "result", "result": "ok", "is_error": False})
    captured = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        return FakeProcess(stdout, b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    await run_claude_code(
        "prompt",
        cwd=tmp_path,
        resume_session_id="sess-9",
        extra_dirs=[tmp_path / "other"],
        permission_mode="acceptEdits",
    )

    args = captured["args"]
    assert "--resume" in args and "sess-9" in args
    assert "--add-dir" in args
    assert "--permission-mode" in args and "acceptEdits" in args


async def test_run_claude_code_raises_on_error_result(monkeypatch, tmp_path):
    stdout = _lines({"type": "result", "result": "boom", "is_error": True})

    async def fake_exec(*args, **kwargs):
        return FakeProcess(stdout, b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(ClaudeCliError, match="reported an error result"):
        await run_claude_code("prompt", cwd=tmp_path)


async def test_run_claude_code_raises_on_nonzero_exit_with_no_stdout(monkeypatch, tmp_path):
    async def fake_exec(*args, **kwargs):
        return FakeProcess(b"", b"some stderr", 1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(ClaudeCliError, match="exited 1"):
        await run_claude_code("prompt", cwd=tmp_path)


async def test_run_claude_code_skips_blank_lines(monkeypatch, tmp_path):
    stdout = b"\n   \n" + _lines({"type": "result", "result": "ok", "is_error": False})

    async def fake_exec(*args, **kwargs):
        return FakeProcess(stdout, b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await run_claude_code("prompt", cwd=tmp_path)
    assert result.final_text == "ok"


async def test_run_claude_code_handles_unparsable_json_line(monkeypatch, tmp_path):
    stdout = b"not json\n" + _lines({"type": "result", "result": "ok", "is_error": False})

    async def fake_exec(*args, **kwargs):
        return FakeProcess(stdout, b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await run_claude_code("prompt", cwd=tmp_path)
    assert result.final_text == "ok"


async def test_run_claude_code_timeout_kills_process(monkeypatch, tmp_path):
    process = FakeProcess(b"", b"", 0)

    async def fake_exec(*args, **kwargs):
        return process

    async def fake_wait_for(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError()

    killed = {}
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(claude_cli, "_kill_process_group", lambda p: killed.setdefault("called", True))

    with pytest.raises(ClaudeCliTimeoutError):
        await run_claude_code("prompt", cwd=tmp_path, timeout_s=1)

    assert killed.get("called") is True


def test_kill_process_group_kills_the_process_group(monkeypatch):
    class FakeProc:
        pid = 4242

    killed = {}
    monkeypatch.setattr("os.getpgid", lambda pid: 9999)
    monkeypatch.setattr("os.killpg", lambda pgid, sig: killed.setdefault("args", (pgid, sig)))

    _kill_process_group(FakeProc())

    import signal as signal_mod

    assert killed["args"] == (9999, signal_mod.SIGKILL)


def test_kill_process_group_swallows_missing_process(monkeypatch):
    class FakeProc:
        pid = 999

    def fake_getpgid(pid):
        raise ProcessLookupError()

    monkeypatch.setattr("os.getpgid", fake_getpgid)
    _kill_process_group(FakeProc())  # should not raise


def test_summarize_events_defaults_when_empty():
    result = _summarize_events([])
    assert result.session_id is None
    assert result.final_text == ""
    assert result.is_error is False
    assert result.raw_events == []


def test_summarize_events_ignores_unrelated_event_types():
    result = _summarize_events([{"type": "unparsed", "raw": "garbage"}])
    assert result.final_text == ""
