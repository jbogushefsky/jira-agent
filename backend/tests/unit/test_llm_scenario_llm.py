from app.llm import scenario_llm as mod


async def test_generate_test_scenarios_builds_prompt_and_parses_result(monkeypatch):
    captured = {}

    class FakeStructuredLLM:
        async def ainvoke(self, prompt):
            captured["prompt"] = prompt
            return mod.TestScenarioList(
                scenarios=[mod.TestScenario(scenario_id="TC-01", acceptance_criterion="ac1", title="t1", body="b1")]
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeStructuredLLM()

    monkeypatch.setattr(mod, "_build_llm", lambda: FakeLLM())

    result = await mod.generate_test_scenarios(
        ticket_key="PROJ-1", summary="s", description="d", acceptance_criteria=["ac1", "ac2"]
    )

    assert len(result) == 1
    assert result[0].scenario_id == "TC-01"
    assert "PROJ-1" in captured["prompt"]
    assert "ac1" in captured["prompt"]
    assert "TC-01" in captured["prompt"]  # rubric instructions got inlined


async def test_generate_test_scenarios_handles_missing_summary_and_criteria(monkeypatch):
    class FakeStructuredLLM:
        async def ainvoke(self, prompt):
            return mod.TestScenarioList(scenarios=[])

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeStructuredLLM()

    monkeypatch.setattr(mod, "_build_llm", lambda: FakeLLM())

    result = await mod.generate_test_scenarios(
        ticket_key="PROJ-2", summary=None, description=None, acceptance_criteria=[]
    )
    assert result == []


def test_build_llm_constructs_chat_anthropic():
    assert mod._build_llm() is not None
