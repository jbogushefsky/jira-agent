from unittest.mock import AsyncMock

from app.graph.nodes import update_ticket_description as mod


async def test_update_ticket_description_calls_jira(monkeypatch):
    fake_jira = AsyncMock()
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    result = await mod.update_ticket_description.__wrapped__(
        {"ticket_key": "PROJ-1", "generated_description": "new text"}
    )
    assert result == {}
    fake_jira.update_description.assert_awaited_once_with("PROJ-1", "new text")


async def test_update_ticket_description_handles_missing_description(monkeypatch):
    fake_jira = AsyncMock()
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    await mod.update_ticket_description.__wrapped__({"ticket_key": "PROJ-1"})
    fake_jira.update_description.assert_awaited_once_with("PROJ-1", "(no description generated)")
