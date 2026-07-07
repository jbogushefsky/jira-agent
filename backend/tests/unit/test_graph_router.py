from app.graph.router import continue_or_fail, route_after_fetch


def test_route_after_fetch_returns_transition_when_no_error():
    assert route_after_fetch({"transition": "to_in_dev"}) == "to_in_dev"


def test_route_after_fetch_returns_handle_failure_on_error():
    assert route_after_fetch({"transition": "to_in_dev", "error": "boom"}) == "handle_failure"


def test_continue_or_fail_returns_next_node_when_no_error():
    router = continue_or_fail("next_step")
    assert router({}) == "next_step"


def test_continue_or_fail_returns_handle_failure_on_error():
    router = continue_or_fail("next_step")
    assert router({"error": "boom"}) == "handle_failure"
