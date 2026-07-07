from unittest.mock import AsyncMock

from app.graph.nodes import review_requirement_ambiguity as mod
from app.llm.ambiguity_llm import AmbiguityQuestion


async def test_review_requirement_ambiguity_passes_through_model_dump(monkeypatch):
    questions = [
        AmbiguityQuestion(requirement="req A", question="What does 'fast' mean here?"),
        AmbiguityQuestion(requirement="req B", question="Which browsers must this support?"),
    ]
    fake_review = AsyncMock(return_value=questions)
    monkeypatch.setattr(mod, "_review", fake_review)

    state = {
        "ticket_key": "PROJ-1",
        "summary": "s",
        "description": "d",
        "acceptance_criteria": ["a"],
    }
    result = await mod.review_requirement_ambiguity.__wrapped__(state)

    assert len(result["ambiguity_questions"]) == 2
    assert result["ambiguity_questions"][0]["requirement"] == "req A"
    fake_review.assert_awaited_once_with(
        ticket_key="PROJ-1", summary="s", description="d", acceptance_criteria=["a"]
    )


async def test_review_requirement_ambiguity_handles_empty_result(monkeypatch):
    monkeypatch.setattr(mod, "_review", AsyncMock(return_value=[]))
    result = await mod.review_requirement_ambiguity.__wrapped__({"ticket_key": "PROJ-1"})
    assert result == {"ambiguity_questions": []}
