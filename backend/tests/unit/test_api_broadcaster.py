import asyncio

from app.api.broadcaster import FlowEventBroadcaster


async def test_subscribe_returns_a_queue():
    b = FlowEventBroadcaster()
    q = b.subscribe()
    assert isinstance(q, asyncio.Queue)


async def test_publish_delivers_to_subscribers():
    b = FlowEventBroadcaster()
    q = b.subscribe()
    await b.publish("step_started", {"a": 1})
    assert q.get_nowait() == {"event": "step_started", "data": {"a": 1}}


async def test_unsubscribe_stops_delivery():
    b = FlowEventBroadcaster()
    q = b.subscribe()
    b.unsubscribe(q)
    await b.publish("evt", {})
    assert q.empty()


async def test_publish_with_no_subscribers_is_a_noop():
    b = FlowEventBroadcaster()
    await b.publish("evt", {})


async def test_publish_warns_but_does_not_raise_when_queue_full():
    b = FlowEventBroadcaster()
    q = b.subscribe()
    for _ in range(100):
        q.put_nowait({"event": "x", "data": {}})
    await b.publish("overflow", {})  # queue full -> logged, not raised
