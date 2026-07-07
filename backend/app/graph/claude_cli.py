import asyncio
import json
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path

from langsmith import traceable

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class ClaudeCliResult:
    session_id: str | None
    final_text: str
    is_error: bool
    duration_ms: int | None
    total_cost_usd: float | None
    raw_events: list[dict] = field(default_factory=list)


class ClaudeCliError(Exception):
    pass


class ClaudeCliTimeoutError(ClaudeCliError):
    pass


@traceable(run_type="tool", name="claude_code_cli")
async def run_claude_code(
    prompt: str,
    *,
    cwd: Path,
    allowed_tools: str = "",
    permission_mode: str | None = None,
    resume_session_id: str | None = None,
    extra_dirs: list[Path] | None = None,
    timeout_s: int | None = None,
) -> ClaudeCliResult:
    """Invokes the Claude Code CLI headlessly (ANTHROPIC_API_KEY auth, no login step)
    and parses its newline-delimited stream-json output.
    """
    timeout_s = timeout_s or settings.claude_cli_timeout_seconds

    args = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        settings.claude_model,
    ]
    if allowed_tools:
        args += ["--allowedTools", allowed_tools]
    else:
        args += ["--allowedTools", ""]
    if permission_mode:
        args += ["--permission-mode", permission_mode]
    if resume_session_id:
        args += ["--resume", resume_session_id]
    for extra_dir in extra_dirs or []:
        args += ["--add-dir", str(extra_dir)]

    env = {**os.environ, "ANTHROPIC_API_KEY": settings.anthropic_api_key}

    logger.info("claude_cli_start", cwd=str(cwd), allowed_tools=allowed_tools, resume=resume_session_id)

    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        _kill_process_group(process)
        raise ClaudeCliTimeoutError(f"claude CLI timed out after {timeout_s}s") from exc

    if process.returncode != 0 and not stdout:
        raise ClaudeCliError(f"claude CLI exited {process.returncode}: {stderr.decode(errors='replace')}")

    events: list[dict] = []
    for line in stdout.decode(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "unparsed", "raw": line})

    result = _summarize_events(events)
    if result.is_error:
        # e.g. a billing/API error surfaced inside a "successful" CLI exit (returncode 0) —
        # without this, the node would treat the error text as real output (recommendations,
        # code-change summary, ...) and the step/flow would report "succeeded".
        raise ClaudeCliError(f"claude CLI reported an error result: {result.final_text}")
    return result


def _summarize_events(events: list[dict]) -> ClaudeCliResult:
    session_id = None
    final_text = ""
    is_error = False
    duration_ms = None
    total_cost_usd = None

    for event in events:
        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init":
            session_id = event.get("session_id")
        elif etype == "result":
            final_text = event.get("result", final_text)
            is_error = bool(event.get("is_error", False))
            duration_ms = event.get("duration_ms")
            total_cost_usd = event.get("total_cost_usd")
        elif etype == "assistant":
            message = event.get("message", {})
            for block in message.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    final_text = block.get("text", final_text)

    return ClaudeCliResult(
        session_id=session_id,
        final_text=final_text,
        is_error=is_error,
        duration_ms=duration_ms,
        total_cost_usd=total_cost_usd,
        raw_events=events,
    )


def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
