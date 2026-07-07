from unittest.mock import AsyncMock

from app.graph.nodes import generate_test_scenarios as mod


class FakeScenario:
    def __init__(self, **kw):
        self._data = kw

    def model_dump(self):
        return dict(self._data)


async def test_generate_test_scenarios_passes_through_model_dump(monkeypatch):
    scenarios = [
        FakeScenario(scenario_id="TC-01", acceptance_criterion="a", title="t1", body="b1"),
        FakeScenario(scenario_id="TC-02", acceptance_criterion="a", title="t2", body="b2"),
    ]
    fake_generate = AsyncMock(return_value=scenarios)
    monkeypatch.setattr(mod, "_generate", fake_generate)

    state = {"ticket_key": "PROJ-1", "summary": "s", "description": "d", "acceptance_criteria": ["a"]}
    result = await mod.generate_test_scenarios.__wrapped__(state)

    assert len(result["test_scenarios"]) == 2
    assert result["test_scenarios"][0]["scenario_id"] == "TC-01"
    fake_generate.assert_awaited_once_with(
        ticket_key="PROJ-1", summary="s", description="d", acceptance_criteria=["a"]
    )


async def test_generate_test_scenarios_handles_empty_result(monkeypatch):
    monkeypatch.setattr(mod, "_generate", AsyncMock(return_value=[]))
    result = await mod.generate_test_scenarios.__wrapped__({"ticket_key": "PROJ-1"})
    assert result == {"test_scenarios": []}
