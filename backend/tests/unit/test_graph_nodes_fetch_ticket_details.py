from unittest.mock import AsyncMock

from app.graph.nodes import fetch_ticket_details as mod


async def test_fetch_ticket_details_extracts_fields(monkeypatch):
    fake_jira = AsyncMock()
    fake_jira.get_issue = AsyncMock(
        return_value={
            "fields": {
                "summary": "Project: dice-roll add reset",
                "description": "Acceptance Criteria:\n- one\n- two",
            }
        }
    )
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    result = await mod.fetch_ticket_details.__wrapped__({"ticket_key": "PROJ-1"})

    assert result["summary"] == "Project: dice-roll add reset"
    assert result["project_name"] == "dice-roll"
    assert result["acceptance_criteria"] == ["one", "two"]


async def test_fetch_ticket_details_handles_flat_issue_shape(monkeypatch):
    fake_jira = AsyncMock()
    fake_jira.get_issue = AsyncMock(return_value={"summary": "no project ref", "description": None})
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    result = await mod.fetch_ticket_details.__wrapped__({"ticket_key": "PROJ-2"})
    assert result["project_name"] is None
    assert result["acceptance_criteria"] == []
