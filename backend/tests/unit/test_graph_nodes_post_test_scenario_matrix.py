from unittest.mock import AsyncMock

from app.graph.nodes import post_test_scenario_matrix as mod


async def test_post_test_scenario_matrix_appends_below_existing_description(monkeypatch):
    fake_jira = AsyncMock()
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    state = {
        "ticket_key": "PROJ-1",
        "description": "Original description text",
        "test_scenarios": [{"scenario_id": "TC-01", "acceptance_criterion": "a", "title": "t1", "body": "line1\nline2"}],
    }
    result = await mod.post_test_scenario_matrix.__wrapped__(state)

    assert result == {}
    fake_jira.update_description.assert_awaited_once()
    args, _ = fake_jira.update_description.call_args
    assert args[0] == "PROJ-1"
    new_description = args[1]
    assert new_description.startswith("Original description text")
    assert "Test Scenario Traceability Matrix" in new_description
    assert "TC-01" in new_description
    assert "line1<br>line2" in new_description


async def test_post_test_scenario_matrix_noop_when_no_scenarios(monkeypatch):
    fake_jira = AsyncMock()
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    result = await mod.post_test_scenario_matrix.__wrapped__({"ticket_key": "PROJ-1", "test_scenarios": []})
    assert result == {}
    fake_jira.update_description.assert_not_awaited()


def test_escape_cell_escapes_pipes_and_newlines():
    assert mod._escape_cell("a|b\nc") == "a\\|b<br>c"


def test_build_matrix_handles_missing_fields():
    matrix = mod._build_matrix([{}])
    assert "(unassigned)" in matrix
    assert "(none)" in matrix
    assert "(untitled)" in matrix
