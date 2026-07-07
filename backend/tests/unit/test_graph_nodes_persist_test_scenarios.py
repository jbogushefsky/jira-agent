import uuid
from unittest.mock import AsyncMock

from app.graph.nodes import persist_test_scenarios as mod
from tests.helpers import make_fake_session_scope


async def test_persist_test_scenarios_stores_each_scenario(monkeypatch):
    add_scenario = AsyncMock()
    monkeypatch.setattr(mod.repo, "add_test_scenario", add_scenario)
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    state = {
        "flow_id": str(uuid.uuid4()),
        "ticket_id": str(uuid.uuid4()),
        "test_scenarios": [{"scenario_id": "TC-01", "acceptance_criterion": "a", "title": "t", "body": "b"}],
    }
    result = await mod.persist_test_scenarios.__wrapped__(state)

    assert result == {"scenarios_persisted": 1}
    add_scenario.assert_awaited_once()
    assert add_scenario.call_args.kwargs["scenario_id"] == "TC-01"


async def test_persist_test_scenarios_handles_empty_list(monkeypatch):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    result = await mod.persist_test_scenarios.__wrapped__(
        {"flow_id": str(uuid.uuid4()), "ticket_id": str(uuid.uuid4())}
    )
    assert result == {"scenarios_persisted": 0}


async def test_persist_test_scenarios_defaults_missing_title_and_body(monkeypatch):
    add_scenario = AsyncMock()
    monkeypatch.setattr(mod.repo, "add_test_scenario", add_scenario)
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    state = {
        "flow_id": str(uuid.uuid4()),
        "ticket_id": str(uuid.uuid4()),
        "test_scenarios": [{}],
    }
    await mod.persist_test_scenarios.__wrapped__(state)
    assert add_scenario.call_args.kwargs["scenario_title"] == "Untitled scenario"
    assert add_scenario.call_args.kwargs["scenario_body"] == ""
