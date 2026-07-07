import uuid
from unittest.mock import AsyncMock

import pytest

from app.api.broadcaster import broadcaster
from app.db import repository as repo
from app.graph.nodes.common import with_step_tracking
from tests.helpers import make_fake_session_scope


@pytest.fixture(autouse=True)
def patch_broadcaster(monkeypatch):
    fake_publish = AsyncMock()
    monkeypatch.setattr(broadcaster, "publish", fake_publish)
    return fake_publish


@pytest.fixture
def patch_repo(monkeypatch):
    fake_step = type("Step", (), {"id": uuid.uuid4()})()
    start = AsyncMock(return_value=fake_step)
    finish = AsyncMock()
    monkeypatch.setattr(repo, "start_flow_step", start)
    monkeypatch.setattr(repo, "finish_flow_step", finish)
    return start, finish


def test_with_step_tracking_exposes_step_name_for_graph_introspection():
    @with_step_tracking("my-step")
    async def node(state):
        return {}

    assert node.step_name == "my-step"


async def test_with_step_tracking_success_path(monkeypatch, patch_repo, patch_broadcaster):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr("app.graph.nodes.common.session_scope", scope)

    @with_step_tracking("my-step")
    async def node(state):
        return {"result": "ok"}

    result = await node({"flow_id": str(uuid.uuid4()), "step_order": 0})

    assert result["result"] == "ok"
    assert result["step_order"] == 1
    start, finish = patch_repo
    start.assert_awaited_once()
    finish.assert_awaited_once()
    assert finish.call_args.kwargs["status"] == "succeeded"
    assert patch_broadcaster.await_count == 2  # step_started, step_updated


async def test_with_step_tracking_failure_path(monkeypatch, patch_repo, patch_broadcaster):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr("app.graph.nodes.common.session_scope", scope)

    @with_step_tracking("my-failing-step")
    async def node(state):
        raise ValueError("boom")

    result = await node({"flow_id": str(uuid.uuid4()), "step_order": 2})

    assert result["error"] == "my-failing-step: boom"
    assert result["step_order"] == 3
    start, finish = patch_repo
    assert finish.call_args.kwargs["status"] == "failed"
    assert finish.call_args.kwargs["error"] == "boom"


async def test_with_step_tracking_handles_none_update(monkeypatch, patch_repo, patch_broadcaster):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr("app.graph.nodes.common.session_scope", scope)

    @with_step_tracking("noop-step")
    async def node(state):
        return None

    result = await node({"flow_id": str(uuid.uuid4()), "step_order": 0})
    assert result["step_order"] == 1


async def test_with_step_tracking_strips_underscore_keys_from_input(monkeypatch, patch_repo, patch_broadcaster):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr("app.graph.nodes.common.session_scope", scope)

    @with_step_tracking("step")
    async def node(state):
        return {}

    await node({"flow_id": str(uuid.uuid4()), "step_order": 0, "_private": "hidden", "visible": "yes"})

    start, _finish = patch_repo
    input_payload = start.call_args.kwargs["input_payload"]
    assert "_private" not in input_payload
    assert input_payload["visible"] == "yes"
