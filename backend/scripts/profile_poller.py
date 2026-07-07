"""Profile a single run of the poller's poll_jira_job with cProfile.

Run inside the backend container (needs the same Postgres/mcp-atlassian access poll_jira_job
normally has via the scheduler):

    docker exec jira-agent-backend-1 python scripts/profile_poller.py

This calls the exact same poll_jira_job() the APScheduler job already invokes every
poll_interval_seconds — running it here doesn't do anything the running scheduler wouldn't
already do on its own tick; it just profiles one specific invocation of it.

cProfile only shows CPU time, not time spent awaiting I/O (the MCP search call, DB
round-trips) — most of poll_jira_job's wall-clock time will show up as time inside the
low-level socket/asyncio read calls, not as meaningful jira-agent function names. Look at
tottime (self time) on jira-agent's own functions (ticket_parsing, diff, repository) for the
CPU-bound part of the picture; use LangSmith/OpenTelemetry traces (already wired up) for the
I/O-latency picture instead.
"""

import asyncio
import cProfile
import os
import pstats
import sys

# Running this as `python scripts/profile_poller.py` puts sys.path[0] at scripts/, not the
# repo root — so app/ isn't importable unless we add it ourselves (avoids relying on
# PYTHONPATH/cwd tricks that don't survive every invocation style).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.poller.scheduler import poll_jira_job  # noqa: E402


def main() -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        asyncio.run(poll_jira_job())
    finally:
        profiler.disable()

    stats = pstats.Stats(profiler, stream=sys.stdout)
    print("\n=== by cumulative time (function + everything it called) ===")
    stats.sort_stats("cumulative").print_stats(20)
    print("\n=== by self time (time in the function itself) ===")
    stats.sort_stats("tottime").print_stats(20)


if __name__ == "__main__":
    main()
