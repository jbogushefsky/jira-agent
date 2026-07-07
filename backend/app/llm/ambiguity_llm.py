from pathlib import Path

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from app.config import get_settings

settings = get_settings()

_AMBIGUITY_INSTRUCTIONS = (
    Path(__file__).resolve().parent.parent / "graph" / "prompts" / "ambiguity_review_instructions.md"
).read_text(encoding="utf-8")


class AmbiguityQuestion(BaseModel):
    requirement: str = Field(description="The ambiguous requirement or statement, quoted or closely paraphrased")
    question: str = Field(description="A specific, answerable clarifying question that resolves the ambiguity")


class AmbiguityReview(BaseModel):
    questions: list[AmbiguityQuestion]


_PROMPT_TEMPLATE = """You are reviewing Jira ticket {ticket_key} for requirement ambiguity, triggered by its move to 'AI - Requirement Review'.

Summary: {summary}

Description:
{description}

Acceptance criteria:
{criteria}

{ambiguity_instructions}"""


def _build_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.claude_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
    )


async def review_ambiguity(
    *, ticket_key: str, summary: str | None, description: str | None, acceptance_criteria: list[str]
) -> list[AmbiguityQuestion]:
    criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria) or "(none listed explicitly)"
    prompt = _PROMPT_TEMPLATE.format(
        ticket_key=ticket_key,
        summary=summary or "(no summary)",
        description=description or "(no description)",
        criteria=criteria_text,
        ambiguity_instructions=_AMBIGUITY_INSTRUCTIONS,
    )

    llm = _build_llm().with_structured_output(AmbiguityReview)
    result: AmbiguityReview = await llm.ainvoke(prompt)
    return result.questions
