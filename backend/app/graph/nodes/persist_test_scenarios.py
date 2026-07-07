import uuid

from app.db import repository as repo
from app.db.session import session_scope
from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState


@with_step_tracking("persist-test-scenarios")
async def persist_test_scenarios(state: GraphState) -> dict:
    scenarios = state.get("test_scenarios", [])
    flow_id = uuid.UUID(state["flow_id"])
    ticket_id = uuid.UUID(state["ticket_id"])

    async with session_scope() as session:
        for scenario in scenarios:
            await repo.add_test_scenario(
                session,
                flow_id=flow_id,
                ticket_id=ticket_id,
                scenario_id=scenario.get("scenario_id"),
                acceptance_criterion=scenario.get("acceptance_criterion"),
                scenario_title=scenario.get("title", "Untitled scenario"),
                scenario_body=scenario.get("body", ""),
            )

    return {"scenarios_persisted": len(scenarios)}
