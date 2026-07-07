import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.mcp_server import server


@pytest.fixture(autouse=True)
def fake_session_scope(monkeypatch):
    @asynccontextmanager
    async def _scope():
        yield AsyncMock()

    monkeypatch.setattr(server, "session_scope", _scope)


async def test_list_processed_tickets(monkeypatch):
    async def fake_list(session, *, status=None, limit=50):
        return ([{"key": "PROJ-1", "lastProcessedAt": datetime.now(timezone.utc)}], 1)

    monkeypatch.setattr(server.repo, "list_processed_tickets", fake_list)
    result = await server.list_processed_tickets()
    assert result[0]["key"] == "PROJ-1"
    assert isinstance(result[0]["lastProcessedAt"], str)


async def test_get_ticket_flow(monkeypatch):
    flow = SimpleNamespace(
        id=uuid.uuid4(),
        transition_type="to_in_dev",
        status="succeeded",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        error_message=None,
    )

    async def fake_flows(session, ticket_key):
        return [flow]

    monkeypatch.setattr(server.repo, "get_flows_for_ticket", fake_flows)
    result = await server.get_ticket_flow("PROJ-1")
    assert result[0]["transitionType"] == "to_in_dev"
    assert result[0]["completedAt"] is None


async def test_get_flow_step_io(monkeypatch):
    step = SimpleNamespace(
        id=uuid.uuid4(), step_name="fetch", step_order=1, status="succeeded", input={}, output={}, error=None
    )

    async def fake_steps(session, flow_id):
        return [step]

    monkeypatch.setattr(server.repo, "get_flow_steps", fake_steps)
    result = await server.get_flow_step_io(str(uuid.uuid4()))
    assert result[0]["name"] == "fetch"


async def test_get_ticket_status_history_found(monkeypatch):
    ticket = SimpleNamespace(id=uuid.uuid4())
    history = SimpleNamespace(from_status="To Do", to_status="In Progress", detected_at=datetime.now(timezone.utc))

    async def fake_get_ticket(session, key):
        return ticket

    async def fake_history(session, ticket_id):
        return [history]

    monkeypatch.setattr(server.repo, "get_ticket_by_key", fake_get_ticket)
    monkeypatch.setattr(server.repo, "get_status_history", fake_history)

    result = await server.get_ticket_status_history("PROJ-1")
    assert result[0]["toStatus"] == "In Progress"


async def test_get_ticket_status_history_ticket_not_found(monkeypatch):
    async def fake_get_ticket(session, key):
        return None

    monkeypatch.setattr(server.repo, "get_ticket_by_key", fake_get_ticket)
    result = await server.get_ticket_status_history("NOPE-1")
    assert result == []
