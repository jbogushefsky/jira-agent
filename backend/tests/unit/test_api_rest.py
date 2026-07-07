import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import rest
from app.db.session import get_session


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(rest.router, prefix="/api")

    async def _fake_get_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _fake_get_session
    return TestClient(app)


def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_config(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["triggerStatuses"], list)
    assert "AI - Build Story" in body["triggerStatuses"]
    assert isinstance(body["jiraProjectKeys"], list)


def test_get_graph_definition(client):
    response = client.get("/api/graph")
    assert response.status_code == 200
    body = response.json()
    assert "fetch_ticket_details" in body["mermaid"]
    assert body["nodeStepNames"]["fetch_ticket_details"] == "fetch-ticket-details"


def test_list_tickets(client, monkeypatch):
    captured = {}

    async def fake_list(session, *, status=None, project=None, project_key=None, limit=50, offset=0):
        captured["project_key"] = project_key
        return (
            [
                {
                    "key": "PROJ-1",
                    "title": "t",
                    "jiraStatus": "In Dev",
                    "project": "dice-roll",
                    "projectKey": "PROJ",
                    "lastProcessedAt": datetime.now(timezone.utc),
                    "overallFlowStatus": "succeeded",
                    "latestFlowId": None,
                }
            ],
            1,
        )

    monkeypatch.setattr(rest.repo, "list_processed_tickets", fake_list)
    response = client.get("/api/tickets?projectKey=PROJ")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["key"] == "PROJ-1"
    assert body["items"][0]["projectKey"] == "PROJ"
    assert captured["project_key"] == "PROJ"


def test_get_ticket_detail_found(client, monkeypatch):
    ticket = SimpleNamespace(
        id=uuid.uuid4(),
        jira_key="PROJ-1",
        summary="t",
        last_seen_status="In Dev",
        target_project_name="dice-roll",
    )

    async def fake_get_ticket(session, key):
        return ticket

    async def fake_history(session, ticket_id):
        return []

    monkeypatch.setattr(rest.repo, "get_ticket_by_key", fake_get_ticket)
    monkeypatch.setattr(rest.repo, "get_status_history", fake_history)

    response = client.get("/api/tickets/PROJ-1")
    assert response.status_code == 200
    assert response.json()["key"] == "PROJ-1"


def test_get_ticket_detail_not_found(client, monkeypatch):
    async def fake_get_ticket(session, key):
        return None

    monkeypatch.setattr(rest.repo, "get_ticket_by_key", fake_get_ticket)
    response = client.get("/api/tickets/NOPE-1")
    assert response.status_code == 404


def test_get_ticket_flows(client, monkeypatch):
    flow = SimpleNamespace(
        id=uuid.uuid4(),
        transition_type="to_in_dev",
        status="succeeded",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )

    async def fake_flows(session, ticket_key):
        return [flow]

    async def fake_steps(session, flow_id):
        return [SimpleNamespace()]

    monkeypatch.setattr(rest.repo, "get_flows_for_ticket", fake_flows)
    monkeypatch.setattr(rest.repo, "get_flow_steps", fake_steps)

    response = client.get("/api/tickets/PROJ-1/flows")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["triggerStatus"] == "In Dev"
    assert body[0]["stepCount"] == 1


def test_get_flow_found(client, monkeypatch):
    flow_id = uuid.uuid4()
    flow = SimpleNamespace(
        id=flow_id,
        transition_type="to_build_story",
        status="succeeded",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )

    async def fake_get_flow(session, fid):
        return flow

    async def fake_steps(session, fid):
        return []

    monkeypatch.setattr(rest.repo, "get_flow", fake_get_flow)
    monkeypatch.setattr(rest.repo, "get_flow_steps", fake_steps)

    response = client.get(f"/api/flows/{flow_id}")
    assert response.status_code == 200
    assert response.json()["triggerStatus"] == "AI - Build Story"


def test_get_flow_not_found(client, monkeypatch):
    async def fake_get_flow(session, fid):
        return None

    monkeypatch.setattr(rest.repo, "get_flow", fake_get_flow)
    response = client.get(f"/api/flows/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_flow_steps(client, monkeypatch):
    step = SimpleNamespace(
        id=uuid.uuid4(),
        step_name="fetch-ticket-details",
        step_order=1,
        status="succeeded",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_ms=100,
    )

    async def fake_steps(session, flow_id):
        return [step]

    monkeypatch.setattr(rest.repo, "get_flow_steps", fake_steps)
    response = client.get(f"/api/flows/{uuid.uuid4()}/steps")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "fetch-ticket-details"


def test_get_step_detail_found_with_langsmith_url(client, monkeypatch):
    step_id = uuid.uuid4()
    flow_id = uuid.uuid4()
    step = SimpleNamespace(
        id=step_id,
        flow_id=flow_id,
        step_name="evaluate",
        status="succeeded",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        input={},
        output={},
        error=None,
    )
    flow = SimpleNamespace(id=flow_id, langsmith_run_id="run-1")

    async def fake_step(session, sid):
        return step

    async def fake_flow(session, fid):
        return flow

    monkeypatch.setattr(rest.repo, "get_step", fake_step)
    monkeypatch.setattr(rest.repo, "get_flow", fake_flow)

    response = client.get(f"/api/steps/{step_id}")
    assert response.status_code == 200
    assert response.json()["langsmithTraceUrl"].startswith("https://smith.langchain.com")


def test_get_step_detail_not_found(client, monkeypatch):
    async def fake_step(session, sid):
        return None

    monkeypatch.setattr(rest.repo, "get_step", fake_step)
    response = client.get(f"/api/steps/{uuid.uuid4()}")
    assert response.status_code == 404


def test_replay_step_not_found(client, monkeypatch):
    async def fake_step(session, sid):
        return None

    monkeypatch.setattr(rest.repo, "get_step", fake_step)
    response = client.post(f"/api/steps/{uuid.uuid4()}/replay")
    assert response.status_code == 404


def test_replay_step_rejects_non_failed_step(client, monkeypatch):
    step = SimpleNamespace(id=uuid.uuid4(), flow_id=uuid.uuid4(), step_name="evaluate", status="succeeded", input={})

    async def fake_step(session, sid):
        return step

    monkeypatch.setattr(rest.repo, "get_step", fake_step)
    response = client.post(f"/api/steps/{step.id}/replay")
    assert response.status_code == 400


def test_replay_step_starts_replay_for_failed_step(client, monkeypatch):
    step = SimpleNamespace(
        id=uuid.uuid4(), flow_id=uuid.uuid4(), step_name="evaluate", status="failed", input={"a": 1}
    )

    async def fake_step(session, sid):
        return step

    captured = {}

    def fake_create_task(coro):
        captured["coro"] = coro
        coro.close()  # avoid an "unawaited coroutine" warning; the call args are what we assert on
        return SimpleNamespace()

    def fake_run_replay(*, flow_id, step_name, step_input):
        captured["kwargs"] = {"flow_id": flow_id, "step_name": step_name, "step_input": step_input}
        return _closed_coro()

    async def _closed_coro():
        return None

    monkeypatch.setattr(rest.repo, "get_step", fake_step)
    monkeypatch.setattr(rest, "run_replay", fake_run_replay)
    monkeypatch.setattr(rest.asyncio, "create_task", fake_create_task)

    response = client.post(f"/api/steps/{step.id}/replay")
    assert response.status_code == 202
    assert response.json() == {"status": "replay_started"}
    assert captured["kwargs"] == {"flow_id": step.flow_id, "step_name": "evaluate", "step_input": {"a": 1}}


def test_get_step_detail_no_langsmith_run_id(client, monkeypatch):
    step_id = uuid.uuid4()
    flow_id = uuid.uuid4()
    step = SimpleNamespace(
        id=step_id,
        flow_id=flow_id,
        step_name="evaluate",
        status="failed",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        input=None,
        output=None,
        error="boom",
    )
    flow = SimpleNamespace(id=flow_id, langsmith_run_id=None)

    async def fake_step(session, sid):
        return step

    async def fake_flow(session, fid):
        return flow

    monkeypatch.setattr(rest.repo, "get_step", fake_step)
    monkeypatch.setattr(rest.repo, "get_flow", fake_flow)

    response = client.get(f"/api/steps/{step_id}")
    assert response.json()["langsmithTraceUrl"] is None
