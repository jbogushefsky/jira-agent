import uuid
from unittest.mock import AsyncMock

from app.api.broadcaster import broadcaster
from app.graph.nodes import handle_failure as mod
from tests.helpers import make_fake_session_scope


async def test_handle_failure_marks_failed_and_broadcasts(monkeypatch):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)
    set_status = AsyncMock()
    monkeypatch.setattr(mod.repo, "set_flow_status", set_status)
    publish = AsyncMock()
    monkeypatch.setattr(broadcaster, "publish", publish)

    flow_id = uuid.uuid4()
    result = await mod.handle_failure({"flow_id": str(flow_id), "ticket_key": "PROJ-1", "error": "boom"})

    assert result == {}
    assert set_status.call_args.kwargs["error_message"] == "boom"
    assert publish.call_args.args[1]["error"] == "boom"


async def test_handle_failure_defaults_error_message(monkeypatch):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)
    set_status = AsyncMock()
    monkeypatch.setattr(mod.repo, "set_flow_status", set_status)
    monkeypatch.setattr(broadcaster, "publish", AsyncMock())

    await mod.handle_failure({"flow_id": str(uuid.uuid4()), "ticket_key": None})
    assert set_status.call_args.kwargs["error_message"] == "unknown error"
