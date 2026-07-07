import asyncio

from fastapi import WebSocketDisconnect

from app.api.broadcaster import broadcaster
from app.api.ws import flows_ws


class FakeWebSocket:
    def __init__(self, disconnect_after: int | None = None):
        self.accepted = False
        self.sent = []
        self._disconnect_after = disconnect_after

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.sent.append(message)
        if self._disconnect_after is not None and len(self.sent) >= self._disconnect_after:
            raise WebSocketDisconnect()


async def test_flows_ws_forwards_broadcast_messages_until_disconnect():
    ws = FakeWebSocket(disconnect_after=1)
    task = asyncio.create_task(flows_ws(ws))
    await asyncio.sleep(0.05)  # let the handler subscribe before we publish

    await broadcaster.publish("step_started", {"a": 1})
    await asyncio.wait_for(task, timeout=2)

    assert ws.accepted
    assert ws.sent == [{"event": "step_started", "data": {"a": 1}}]


async def test_flows_ws_unsubscribes_on_cancellation():
    ws = FakeWebSocket()
    task = asyncio.create_task(flows_ws(ws))
    await asyncio.sleep(0.05)

    subscribers_before = len(broadcaster._subscribers)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(broadcaster._subscribers) == subscribers_before - 1
