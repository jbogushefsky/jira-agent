import uuid
from unittest.mock import AsyncMock

from app.graph import graph as mod
from tests.helpers import make_fake_session_scope


def test_build_graph_compiles():
    assert mod.build_graph() is not None


def test_node_step_names_covers_every_tracked_node():
    # finalize_flow/handle_failure aren't wrapped in with_step_tracking, so they're the only
    # two NODE_FUNCTIONS entries expected to be absent from NODE_STEP_NAMES.
    untracked = {"finalize_flow", "handle_failure"}
    assert set(mod.NODE_FUNCTIONS) - set(mod.NODE_STEP_NAMES) == untracked
    assert mod.NODE_STEP_NAMES["fetch_ticket_details"] == "fetch-ticket-details"


def test_get_mermaid_definition_includes_every_node_and_a_conditional_branch():
    mermaid = mod.get_mermaid_definition()
    for node_id in mod.NODE_FUNCTIONS:
        assert node_id in mermaid
    assert "to_story_review" in mermaid  # a labeled conditional edge from fetch_ticket_details
    assert "-.->" in mermaid or "-. " in mermaid  # conditional edges render dashed


def test_get_compiled_graph_is_cached(monkeypatch):
    monkeypatch.setattr(mod, "_compiled_graph", None)
    first = mod.get_compiled_graph()
    second = mod.get_compiled_graph()
    assert first is second


async def test_run_flow_invokes_graph_and_sets_status(monkeypatch):
    set_status = AsyncMock()
    monkeypatch.setattr(mod.repo, "set_flow_status", set_status)
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    fake_graph = type("G", (), {"ainvoke": AsyncMock(return_value=None)})()
    monkeypatch.setattr(mod, "get_compiled_graph", lambda: fake_graph)

    await mod.run_flow(
        flow_id=uuid.uuid4(), ticket_id=uuid.uuid4(), ticket_key="PROJ-1", transition_type="to_in_dev"
    )

    fake_graph.ainvoke.assert_awaited_once()
    assert set_status.await_count == 2
    assert set_status.call_args.kwargs["status"] == "running"


async def test_run_flow_marks_failed_on_exception(monkeypatch):
    set_status = AsyncMock()
    monkeypatch.setattr(mod.repo, "set_flow_status", set_status)
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    fake_graph = type("G", (), {"ainvoke": AsyncMock(side_effect=RuntimeError("boom"))})()
    monkeypatch.setattr(mod, "get_compiled_graph", lambda: fake_graph)

    await mod.run_flow(
        flow_id=uuid.uuid4(), ticket_id=uuid.uuid4(), ticket_key="PROJ-1", transition_type="to_in_dev"
    )

    assert set_status.call_args.kwargs["status"] == "failed"


def test_build_graph_accepts_arbitrary_entry_point():
    assert mod.build_graph(entry_point="generate_code_changes") is not None


def test_node_id_by_step_name_is_reverse_of_node_step_names():
    for node_id, step_name in mod.NODE_STEP_NAMES.items():
        assert mod.NODE_ID_BY_STEP_NAME[step_name] == node_id
    assert len(mod.NODE_ID_BY_STEP_NAME) == len(mod.NODE_STEP_NAMES)


async def test_run_replay_logs_and_returns_on_unknown_step_name(monkeypatch):
    set_status = AsyncMock()
    monkeypatch.setattr(mod.repo, "set_flow_status", set_status)

    await mod.run_replay(flow_id=uuid.uuid4(), step_name="not-a-real-step", step_input={})

    set_status.assert_not_awaited()


async def test_run_replay_invokes_graph_from_replayed_node(monkeypatch):
    set_status = AsyncMock()
    get_flow_steps = AsyncMock(return_value=[object(), object()])
    monkeypatch.setattr(mod.repo, "set_flow_status", set_status)
    monkeypatch.setattr(mod.repo, "get_flow_steps", get_flow_steps)
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    fake_graph = type("G", (), {"ainvoke": AsyncMock(return_value=None)})()
    captured = {}

    def fake_build_graph(entry_point="fetch_ticket_details"):
        captured["entry_point"] = entry_point
        return fake_graph

    monkeypatch.setattr(mod, "build_graph", fake_build_graph)

    step_name = mod.NODE_STEP_NAMES["generate_code_changes"]
    await mod.run_replay(flow_id=uuid.uuid4(), step_name=step_name, step_input={"ticket_key": "PROJ-1"})

    assert captured["entry_point"] == "generate_code_changes"
    fake_graph.ainvoke.assert_awaited_once()
    invoked_state = fake_graph.ainvoke.await_args.args[0]
    assert invoked_state["step_order"] == 2  # restarted from the existing step count, not the input's
    assert invoked_state["ticket_key"] == "PROJ-1"
    assert set_status.call_args.kwargs["status"] == "running"


async def test_run_replay_marks_failed_on_exception(monkeypatch):
    set_status = AsyncMock()
    monkeypatch.setattr(mod.repo, "set_flow_status", set_status)
    monkeypatch.setattr(mod.repo, "get_flow_steps", AsyncMock(return_value=[]))
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)

    fake_graph = type("G", (), {"ainvoke": AsyncMock(side_effect=RuntimeError("boom"))})()
    monkeypatch.setattr(mod, "build_graph", lambda entry_point="fetch_ticket_details": fake_graph)

    step_name = mod.NODE_STEP_NAMES["generate_code_changes"]
    await mod.run_replay(flow_id=uuid.uuid4(), step_name=step_name, step_input={})

    assert set_status.call_args.kwargs["status"] == "failed"
