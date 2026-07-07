from unittest.mock import AsyncMock

from app.graph.nodes import post_ambiguity_questions as mod


async def test_post_ambiguity_questions_appends_below_existing_description(monkeypatch):
    fake_jira = AsyncMock()
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    state = {
        "ticket_key": "PROJ-1",
        "description": "Original description text",
        "ambiguity_questions": [
            {"requirement": "the button should work well on mobile", "question": "What breakpoints?"}
        ],
    }
    result = await mod.post_ambiguity_questions.__wrapped__(state)

    assert result == {}
    fake_jira.update_description.assert_awaited_once()
    args, _ = fake_jira.update_description.call_args
    assert args[0] == "PROJ-1"
    new_description = args[1]
    assert new_description.startswith("Original description text")
    assert "Clarification Questions" in new_description
    assert "What breakpoints?" in new_description
    assert "_(pending)_" in new_description


async def test_post_ambiguity_questions_noop_when_no_ambiguity_found(monkeypatch):
    fake_jira = AsyncMock()
    monkeypatch.setattr(mod, "get_jira_client", lambda: fake_jira)

    result = await mod.post_ambiguity_questions.__wrapped__(
        {"ticket_key": "PROJ-1", "ambiguity_questions": []}
    )
    assert result == {}
    fake_jira.update_description.assert_not_awaited()


def test_build_questions_section_handles_missing_fields():
    section = mod._build_questions_section([{}])
    assert "(unspecified)" in section
    assert "Clarification Questions" in section
