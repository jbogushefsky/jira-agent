import functools
import uuid
from collections.abc import Awaitable, Callable

from app.api.broadcaster import broadcaster
from app.db import repository as repo
from app.db.session import session_scope
from app.graph.state import GraphState
from app.logging_config import get_logger

logger = get_logger(__name__)

NodeFn = Callable[[GraphState], Awaitable[dict]]


def with_step_tracking(step_name: str) -> Callable[[NodeFn], NodeFn]:
    """Wraps a graph node so every invocation is persisted as a `flow_steps` row
    (input/output/status/duration) and broadcast over /ws/flows — this is what
    powers the UI's per-step popup. On failure, sets state["error"] instead of
    raising, so the graph's conditional edges can route to handle_failure.
    """

    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        async def wrapper(state: GraphState) -> dict:
            flow_id = uuid.UUID(state["flow_id"])
            step_order = state.get("step_order", 0) + 1
            step_input = {k: v for k, v in state.items() if not k.startswith("_")}

            async with session_scope() as session:
                step = await repo.start_flow_step(
                    session,
                    flow_id=flow_id,
                    step_name=step_name,
                    step_order=step_order,
                    input_payload=step_input,
                )
                step_id = step.id

            await broadcaster.publish(
                "step_started",
                {"flowId": str(flow_id), "stepId": str(step_id), "name": step_name, "status": "running"},
            )

            try:
                update = await fn(state)
                update = update or {}
                async with session_scope() as session:
                    await repo.finish_flow_step(session, step_id, status="succeeded", output=update)
                await broadcaster.publish(
                    "step_updated",
                    {"flowId": str(flow_id), "stepId": str(step_id), "name": step_name, "status": "succeeded"},
                )
                update["step_order"] = step_order
                return update
            except Exception as exc:  # noqa: BLE001 - deliberately broad: any node failure must not crash the poller
                logger.exception("node_failed", step_name=step_name, flow_id=str(flow_id))
                async with session_scope() as session:
                    await repo.finish_flow_step(session, step_id, status="failed", error=str(exc))
                await broadcaster.publish(
                    "step_updated",
                    {"flowId": str(flow_id), "stepId": str(step_id), "name": step_name, "status": "failed"},
                )
                return {"step_order": step_order, "error": f"{step_name}: {exc}"}

        wrapper.step_name = step_name
        return wrapper

    return decorator
