from app.llm import ambiguity_llm as mod


async def test_review_ambiguity_builds_prompt_and_parses_result(monkeypatch):
    captured = {}

    class FakeStructuredLLM:
        async def ainvoke(self, prompt):
            captured["prompt"] = prompt
            return mod.AmbiguityReview(
                questions=[
                    mod.AmbiguityQuestion(
                        requirement="the button should work well on mobile",
                        question="What specific breakpoint(s) must this button support?",
                    )
                ]
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeStructuredLLM()

    monkeypatch.setattr(mod, "_build_llm", lambda: FakeLLM())

    result = await mod.review_ambiguity(
        ticket_key="PROJ-1", summary="s", description="d", acceptance_criteria=["ac1"]
    )

    assert len(result) == 1
    assert result[0].requirement == "the button should work well on mobile"
    assert "PROJ-1" in captured["prompt"]
    assert "ac1" in captured["prompt"]
    assert "genuine ambiguity" in captured["prompt"]  # rubric instructions got inlined


async def test_review_ambiguity_returns_empty_list_when_no_ambiguity(monkeypatch):
    class FakeStructuredLLM:
        async def ainvoke(self, prompt):
            return mod.AmbiguityReview(questions=[])

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeStructuredLLM()

    monkeypatch.setattr(mod, "_build_llm", lambda: FakeLLM())

    result = await mod.review_ambiguity(
        ticket_key="PROJ-2", summary=None, description=None, acceptance_criteria=[]
    )
    assert result == []


def test_build_llm_constructs_chat_anthropic():
    assert mod._build_llm() is not None
