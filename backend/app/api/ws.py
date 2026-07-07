import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.broadcaster import broadcaster
from app.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.websocket("/ws/flows")
async def flows_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = broadcaster.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        broadcaster.unsubscribe(queue)
