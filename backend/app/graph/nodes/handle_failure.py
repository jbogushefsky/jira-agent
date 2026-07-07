import uuid

from app.api.broadcaster import broadcaster
from app.db import repository as repo
from app.db.session import session_scope
from app.graph.state import GraphState
from app.logging_config import get_logger

logger = get_logger(__name__)


async def handle_failure(state: GraphState) -> dict:
    flow_id = uuid.UUID(state["flow_id"])
    error = state.get("error") or "unknown error"
    logger.error("flow_failed", flow_id=str(flow_id), ticket_key=state.get("ticket_key"), error=error)

    async with session_scope() as session:
        await repo.set_flow_status(session, flow_id, status="failed", error_message=error)

    await broadcaster.publish(
        "flow_updated",
        {"flowId": str(flow_id), "ticketKey": state.get("ticket_key"), "status": "failed", "error": error},
    )
    return {}
