from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.llm.ambiguity_llm import review_ambiguity as _review


@with_step_tracking("review-requirement-ambiguity")
async def review_requirement_ambiguity(state: GraphState) -> dict:
    questions = await _review(
        ticket_key=state["ticket_key"],
        summary=state.get("summary"),
        description=state.get("description"),
        acceptance_criteria=state.get("acceptance_criteria", []),
    )
    return {"ambiguity_questions": [q.model_dump() for q in questions]}
