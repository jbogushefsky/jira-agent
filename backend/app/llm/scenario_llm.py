from pathlib import Path

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from app.config import get_settings

settings = get_settings()

_SCENARIO_INSTRUCTIONS = (
    Path(__file__).resolve().parent.parent / "graph" / "prompts" / "test_scenario_instructions.md"
).read_text(encoding="utf-8")


class TestScenario(BaseModel):
    scenario_id: str = Field(
        description="Unique traceability identifier in the form '{ticket_key}-AC-##-TC-##', "
        "e.g. 'PROJ-42-AC-01-TC-01'"
    )
    acceptance_criterion: str = Field(description="The acceptance criterion this scenario verifies")
    title: str = Field(description="Short scenario title")
    body: str = Field(description="Given/When/Then formatted test scenario")


class TestScenarioList(BaseModel):
    scenarios: list[TestScenario]


_PROMPT_TEMPLATE = """You are documenting test scenarios for Jira ticket {ticket_key}, which just moved to 'AI - Generate Test Scenarios'.

Summary: {summary}

Description:
{description}

Acceptance criteria:
{criteria}

Write at least one Given/When/Then test scenario per acceptance criterion listed above, covering the
happy path and, where relevant, an edge case. Every acceptance criterion must be covered by at least
one scenario.

{scenario_instructions}"""


def _build_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.claude_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
    )


async def generate_test_scenarios(
    *, ticket_key: str, summary: str | None, description: str | None, acceptance_criteria: list[str]
) -> list[TestScenario]:
    criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria) or "(none listed explicitly)"
    prompt = _PROMPT_TEMPLATE.format(
        ticket_key=ticket_key,
        summary=summary or "(no summary)",
        description=description or "(no description)",
        criteria=criteria_text,
        scenario_instructions=_SCENARIO_INSTRUCTIONS,
    )

    llm = _build_llm().with_structured_output(TestScenarioList)
    result: TestScenarioList = await llm.ainvoke(prompt)
    return result.scenarios
