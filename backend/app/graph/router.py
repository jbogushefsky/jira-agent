from app.graph.state import GraphState


def route_after_fetch(state: GraphState) -> str:
    # Returns the transition KEY ("to_story_review"), not the resolved node name — the
    # add_conditional_edges() path map in graph.py does that translation. Returning the
    # node name directly here raised KeyError on every single flow, since "evaluate_ticket"
    # etc. were never keys in that path map.
    if state.get("error"):
        return "handle_failure"
    return state["transition"]


def continue_or_fail(next_node: str):
    def _route(state: GraphState) -> str:
        return "handle_failure" if state.get("error") else next_node

    return _route
