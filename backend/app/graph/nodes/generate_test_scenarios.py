from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.llm.scenario_llm import generate_test_scenarios as _generate


@with_step_tracking("generate-test-scenarios")
async def generate_test_scenarios(state: GraphState) -> dict:
    scenarios = await _generate(
        ticket_key=state["ticket_key"],
        summary=state.get("summary"),
        description=state.get("description"),
        acceptance_criteria=state.get("acceptance_criteria", []),
    )
    return {"test_scenarios": [s.model_dump() for s in scenarios]}
