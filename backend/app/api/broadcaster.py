import asyncio
from typing import Any

from app.logging_config import get_logger

logger = get_logger(__name__)


class FlowEventBroadcaster:
    """In-process pub/sub for /ws/flows.

    Single-instance-only by design (matches the plan's noted limitation) — if the backend
    is ever horizontally scaled, replace this with Postgres LISTEN/NOTIFY or Redis pub/sub.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        message = {"event": event_type, "data": data}
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("ws_subscriber_queue_full", event_type=event_type)


broadcaster = FlowEventBroadcaster()
