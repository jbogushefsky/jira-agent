from unittest.mock import AsyncMock

from app.graph.nodes import post_recommendations as mod


async def test_post_recommendations_adds_comment(monkeypatch):
    fake_jira = AsyncMock()
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    result = await mod.post_recommendations.__wrapped__({"ticket_key": "PROJ-1", "recommendations": "do X"})

    assert result == {}
    fake_jira.add_comment.assert_awaited_once()
    args, _ = fake_jira.add_comment.call_args
    assert args[0] == "PROJ-1"
    assert "do X" in args[1]


async def test_post_recommendations_handles_missing_recommendations(monkeypatch):
    fake_jira = AsyncMock()
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    await mod.post_recommendations.__wrapped__({"ticket_key": "PROJ-1"})
    args, _ = fake_jira.add_comment.call_args
    assert "no recommendations generated" in args[1]
