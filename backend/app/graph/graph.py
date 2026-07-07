import uuid

from langgraph.graph import END, StateGraph

from app.db import repository as repo
from app.db.session import session_scope
from app.graph.nodes.evaluate_ticket import evaluate_ticket
from app.graph.nodes.fetch_ticket_details import fetch_ticket_details
from app.graph.nodes.finalize_flow import finalize_flow
from app.graph.nodes.generate_approach import generate_approach
from app.graph.nodes.generate_code_changes import generate_code_changes
from app.graph.nodes.generate_test_scenarios import generate_test_scenarios
from app.graph.nodes.generate_tests import generate_tests
from app.graph.nodes.handle_failure import handle_failure
from app.graph.nodes.parse_project_reference import parse_project_reference
from app.graph.nodes.persist_test_scenarios import persist_test_scenarios
from app.graph.nodes.post_ambiguity_questions import post_ambiguity_questions
from app.graph.nodes.post_recommendations import post_recommendations
from app.graph.nodes.post_test_scenario_matrix import post_test_scenario_matrix
from app.graph.nodes.review_requirement_ambiguity import review_requirement_ambiguity
from app.graph.nodes.update_ticket_description import update_ticket_description
from app.graph.router import continue_or_fail, route_after_fetch
from app.graph.state import GraphState
from app.logging_config import get_logger

logger = get_logger(__name__)

_compiled_graph = None

# Single source of truth for graph node ids -> node functions: used both to build the graph
# below and (via NODE_STEP_NAMES) to expose which `flow_steps.step_name` each node corresponds
# to over the API, since with_step_tracking's step_name strings ("claude-code-evaluate") don't
# match these node ids ("evaluate_ticket") — the mapping is derived from each function's
# `.step_name` attribute (set by with_step_tracking) rather than hand-duplicated here.
NODE_FUNCTIONS = {
    "fetch_ticket_details": fetch_ticket_details,
    "evaluate_ticket": evaluate_ticket,
    "post_recommendations": post_recommendations,
    "generate_test_scenarios": generate_test_scenarios,
    "persist_test_scenarios": persist_test_scenarios,
    "post_test_scenario_matrix": post_test_scenario_matrix,
    "parse_project_reference": parse_project_reference,
    "generate_code_changes": generate_code_changes,
    "generate_tests": generate_tests,
    "generate_approach": generate_approach,
    "update_ticket_description": update_ticket_description,
    "review_requirement_ambiguity": review_requirement_ambiguity,
    "post_ambiguity_questions": post_ambiguity_questions,
    "finalize_flow": finalize_flow,
    "handle_failure": handle_failure,
}

# finalize_flow/handle_failure aren't wrapped in with_step_tracking (no flow_steps row of their
# own — see run_flow/set_flow_status instead), so they have no `.step_name` and are omitted here.
NODE_STEP_NAMES: dict[str, str] = {
    node_id: fn.step_name for node_id, fn in NODE_FUNCTIONS.items() if hasattr(fn, "step_name")
}

# Reverse of the above — used by run_replay to turn a `flow_steps.step_name` (from the row the
# user clicked "Replay" on) back into the graph node id to re-enter at.
NODE_ID_BY_STEP_NAME: dict[str, str] = {step_name: node_id for node_id, step_name in NODE_STEP_NAMES.items()}


def build_graph(entry_point: str = "fetch_ticket_details"):
    """`entry_point` defaults to the normal flow start, but run_replay builds a graph entering
    at an arbitrary node instead — add_conditional_edges wiring is keyed by source node id, not
    by entry point, so the exact same edges/routing apply regardless of where traversal begins.
    """
    graph = StateGraph(GraphState)

    for node_id, fn in NODE_FUNCTIONS.items():
        graph.add_node(node_id, fn)

    graph.set_entry_point(entry_point)

    graph.add_conditional_edges(
        "fetch_ticket_details",
        route_after_fetch,
        {
            "to_story_review": "evaluate_ticket",
            "to_generate_test_scenarios": "generate_test_scenarios",
            "to_in_dev": "parse_project_reference",
            "to_build_story": "generate_approach",
            "to_requirement_review": "review_requirement_ambiguity",
            "handle_failure": "handle_failure",
        },
    )

    graph.add_conditional_edges(
        "evaluate_ticket",
        continue_or_fail("post_recommendations"),
        {"post_recommendations": "post_recommendations", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "post_recommendations",
        continue_or_fail("finalize_flow"),
        {"finalize_flow": "finalize_flow", "handle_failure": "handle_failure"},
    )

    graph.add_conditional_edges(
        "generate_test_scenarios",
        continue_or_fail("persist_test_scenarios"),
        {"persist_test_scenarios": "persist_test_scenarios", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "persist_test_scenarios",
        continue_or_fail("post_test_scenario_matrix"),
        {"post_test_scenario_matrix": "post_test_scenario_matrix", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "post_test_scenario_matrix",
        continue_or_fail("finalize_flow"),
        {"finalize_flow": "finalize_flow", "handle_failure": "handle_failure"},
    )

    graph.add_conditional_edges(
        "parse_project_reference",
        continue_or_fail("generate_code_changes"),
        {"generate_code_changes": "generate_code_changes", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "generate_code_changes",
        continue_or_fail("generate_tests"),
        {"generate_tests": "generate_tests", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "generate_tests",
        continue_or_fail("finalize_flow"),
        {"finalize_flow": "finalize_flow", "handle_failure": "handle_failure"},
    )

    graph.add_conditional_edges(
        "generate_approach",
        continue_or_fail("update_ticket_description"),
        {"update_ticket_description": "update_ticket_description", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "update_ticket_description",
        continue_or_fail("finalize_flow"),
        {"finalize_flow": "finalize_flow", "handle_failure": "handle_failure"},
    )

    graph.add_conditional_edges(
        "review_requirement_ambiguity",
        continue_or_fail("post_ambiguity_questions"),
        {"post_ambiguity_questions": "post_ambiguity_questions", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "post_ambiguity_questions",
        continue_or_fail("finalize_flow"),
        {"finalize_flow": "finalize_flow", "handle_failure": "handle_failure"},
    )

    graph.add_edge("finalize_flow", END)
    graph.add_edge("handle_failure", END)

    return graph.compile()


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def get_mermaid_definition() -> str:
    """Mermaid flowchart source for the graph's actual wiring — LangGraph renders conditional
    edges (add_conditional_edges) distinctly from unconditional ones, so branches like
    fetch_ticket_details's five-way transition split and every node's route-to-handle_failure
    edge are visible without hand-maintaining a duplicate diagram on the frontend.
    """
    return get_compiled_graph().get_graph().draw_mermaid()


async def run_flow(*, flow_id: uuid.UUID, ticket_id: uuid.UUID, ticket_key: str, transition_type: str) -> None:
    """Entry point invoked by the poller (decoupled from the poll tick via asyncio.create_task)."""
    graph = get_compiled_graph()

    async with session_scope() as session:
        await repo.set_flow_status(session, flow_id, status="running")

    initial_state: GraphState = {
        "flow_id": str(flow_id),
        "ticket_id": str(ticket_id),
        "ticket_key": ticket_key,
        "transition": transition_type,
        "step_order": 0,
    }

    run_id = str(uuid.uuid4())
    config = {
        "run_id": run_id,
        "run_name": f"{ticket_key}:{transition_type}",
        "tags": ["jira-agent", transition_type],
        "metadata": {"ticket_key": ticket_key, "flow_id": str(flow_id)},
    }

    async with session_scope() as session:
        await repo.set_flow_status(session, flow_id, status="running", langsmith_run_id=run_id)

    try:
        await graph.ainvoke(initial_state, config=config)
    except Exception:
        logger.exception("graph_invocation_failed", flow_id=str(flow_id), ticket_key=ticket_key)
        async with session_scope() as session:
            await repo.set_flow_status(
                session, flow_id, status="failed", error_message="unhandled graph invocation error"
            )


async def run_replay(*, flow_id: uuid.UUID, step_name: str, step_input: dict) -> None:
    """Re-runs a single failed step from its own originally-captured input state (the exact
    GraphState `with_step_tracking` recorded right before that node ran) — and, if it succeeds
    this time, continues through the graph's normal routing from there, same as a fresh flow
    would. Entry point invoked by the REST layer's /steps/{id}/replay endpoint, decoupled from
    the request the same way run_flow is decoupled from the poll tick.
    """
    node_id = NODE_ID_BY_STEP_NAME.get(step_name)
    if node_id is None:
        logger.error("replay_unknown_step_name", step_name=step_name, flow_id=str(flow_id))
        return

    async with session_scope() as session:
        existing_steps = await repo.get_flow_steps(session, flow_id)
    # Ignore whatever step_order the original (failed) attempt captured — restart the count from
    # the flow's current total so a replay's steps always sort after everything already recorded,
    # rather than risking a tie with the step being replayed.
    initial_state = {**step_input, "step_order": len(existing_steps)}

    async with session_scope() as session:
        await repo.set_flow_status(session, flow_id, status="running")

    graph = build_graph(entry_point=node_id)

    run_id = str(uuid.uuid4())
    config = {
        "run_id": run_id,
        "run_name": f"replay:{step_name}",
        "tags": ["jira-agent", "replay", step_name],
        "metadata": {"flow_id": str(flow_id), "replayed_step": step_name},
    }

    async with session_scope() as session:
        await repo.set_flow_status(session, flow_id, status="running", langsmith_run_id=run_id)

    try:
        await graph.ainvoke(initial_state, config=config)
    except Exception:
        logger.exception("replay_invocation_failed", flow_id=str(flow_id), step_name=step_name)
        async with session_scope() as session:
            await repo.set_flow_status(
                session, flow_id, status="failed", error_message="unhandled graph invocation error during replay"
            )
