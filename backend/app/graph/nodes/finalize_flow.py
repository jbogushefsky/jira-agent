import uuid

from app.api.broadcaster import broadcaster
from app.db import repository as repo
from app.db.session import session_scope
from app.graph.state import GraphState


async def finalize_flow(state: GraphState) -> dict:
    flow_id = uuid.UUID(state["flow_id"])
    async with session_scope() as session:
        await repo.set_flow_status(session, flow_id, status="succeeded")
    await broadcaster.publish(
        "flow_updated", {"flowId": str(flow_id), "ticketKey": state["ticket_key"], "status": "succeeded"}
    )
    return {}
