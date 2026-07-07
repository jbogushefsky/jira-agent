import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.exc import IntegrityError

from app.poller import scheduler as mod
from tests.helpers import make_fake_session_scope


def test_build_jql_with_configured_keys(monkeypatch):
    monkeypatch.setattr(mod.settings, "jira_project_keys", "PROJ, OTHER")
    assert mod._build_jql() == "project in (PROJ, OTHER) ORDER BY updated DESC"


def test_build_jql_without_configured_keys(monkeypatch):
    monkeypatch.setattr(mod.settings, "jira_project_keys", "")
    assert mod._build_jql() == "project is not EMPTY ORDER BY updated DESC"


async def test_poll_jira_job_processes_each_issue(monkeypatch):
    fake_jira = AsyncMock()
    fake_jira.search_issues = AsyncMock(return_value=[{"key": "PROJ-1"}, {"key": "PROJ-2"}])
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    process_issue = AsyncMock()
    monkeypatch.setattr(mod, "_process_issue", process_issue)

    await mod.poll_jira_job()

    assert process_issue.await_count == 2


async def test_poll_jira_job_handles_search_failure_gracefully(monkeypatch):
    fake_jira = AsyncMock()
    fake_jira.search_issues = AsyncMock(side_effect=RuntimeError("jira down"))
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    await mod.poll_jira_job()  # should not raise


async def test_poll_jira_job_continues_after_one_issue_fails(monkeypatch):
    fake_jira = AsyncMock()
    fake_jira.search_issues = AsyncMock(return_value=[{"key": "PROJ-1"}, {"key": "PROJ-2"}])
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    async def flaky(issue):
        if issue["key"] == "PROJ-1":
            raise RuntimeError("boom")

    monkeypatch.setattr(mod, "_process_issue", flaky)

    await mod.poll_jira_job()  # should not raise despite PROJ-1 failing


async def test_process_issue_skips_when_no_key():
    await mod._process_issue({})


async def test_process_issue_skips_when_no_status():
    await mod._process_issue({"key": "PROJ-1", "fields": {}})


async def test_process_issue_no_transition_returns_early(monkeypatch):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    ticket = MagicMock(id=uuid.uuid4(), last_seen_status="To Do")
    monkeypatch.setattr(mod.repo, "get_ticket_by_key", AsyncMock(return_value=ticket))
    monkeypatch.setattr(mod.repo, "upsert_ticket", AsyncMock(return_value=ticket))

    issue = {"key": "PROJ-1", "fields": {"status": {"name": "To Do"}, "summary": "s", "description": "d"}}
    await mod._process_issue(issue)  # same status -> compute_transition returns None -> early return


async def test_process_issue_triggers_flow_on_valid_transition(monkeypatch):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    ticket = MagicMock(id=uuid.uuid4(), last_seen_status="To Do")
    monkeypatch.setattr(mod.repo, "get_ticket_by_key", AsyncMock(return_value=ticket))
    monkeypatch.setattr(mod.repo, "upsert_ticket", AsyncMock(return_value=ticket))
    monkeypatch.setattr(mod.repo, "record_status_change", AsyncMock(return_value=MagicMock(id=uuid.uuid4())))
    monkeypatch.setattr(mod.repo, "create_flow", AsyncMock(return_value=MagicMock(id=uuid.uuid4())))

    created_tasks = []

    def fake_create_task(coro):
        coro.close()
        created_tasks.append(coro)
        return MagicMock()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    issue = {
        "key": "PROJ-1",
        "fields": {
            "status": {"name": "AI - Story Review"},
            "summary": "s",
            "description": "d",
            "project": {"key": "PROJ"},
        },
    }
    await mod._process_issue(issue)

    assert len(created_tasks) == 1


async def test_process_issue_skips_duplicate_active_flow(monkeypatch):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    ticket = MagicMock(id=uuid.uuid4(), last_seen_status="To Do")
    monkeypatch.setattr(mod.repo, "get_ticket_by_key", AsyncMock(return_value=ticket))
    monkeypatch.setattr(mod.repo, "upsert_ticket", AsyncMock(return_value=ticket))
    monkeypatch.setattr(mod.repo, "record_status_change", AsyncMock(return_value=MagicMock(id=uuid.uuid4())))
    monkeypatch.setattr(mod.repo, "create_flow", AsyncMock(side_effect=IntegrityError("dup", None, None)))

    issue = {
        "key": "PROJ-1",
        "fields": {"status": {"name": "AI - Story Review"}, "summary": "s", "description": "d"},
    }
    await mod._process_issue(issue)  # should not raise


async def test_start_and_stop_scheduler():
    scheduler = mod.start_scheduler()
    try:
        assert scheduler.running
    finally:
        mod.stop_scheduler(scheduler)
