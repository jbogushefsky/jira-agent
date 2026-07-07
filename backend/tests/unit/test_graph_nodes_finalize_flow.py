import uuid
from unittest.mock import AsyncMock

from app.api.broadcaster import broadcaster
from app.graph.nodes import finalize_flow as mod
from tests.helpers import make_fake_session_scope


async def test_finalize_flow_marks_succeeded_and_broadcasts(monkeypatch):
    scope, _session = make_fake_session_scope()
    monkeypatch.setattr(mod, "session_scope", scope)
    set_status = AsyncMock()
    monkeypatch.setattr(mod.repo, "set_flow_status", set_status)
    publish = AsyncMock()
    monkeypatch.setattr(broadcaster, "publish", publish)

    flow_id = uuid.uuid4()
    result = await mod.finalize_flow({"flow_id": str(flow_id), "ticket_key": "PROJ-1"})

    assert result == {}
    set_status.assert_awaited_once()
    assert set_status.call_args.kwargs["status"] == "succeeded"
    publish.assert_awaited_once()
    assert publish.call_args.args[0] == "flow_updated"
    assert publish.call_args.args[1]["status"] == "succeeded"
