"""Standalone ASGI entrypoint for the `jira-agent-mcp` service.

This used to be mounted at `/mcp` inside the main backend's FastAPI app (app/main.py),
sharing its process with the REST/WS API. It's split out here so the MCP surface can be
built, deployed, and scaled independently of the poller/graph/REST service — the two
share this codebase and Postgres, but run as separate containers (see docker-compose.yml's
`jira-agent-mcp` service, which points at this module instead of app.main:app).
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.logging_config import configure_logging, get_logger
from app.mcp_server.server import mcp
from app.observability.otel_setup import configure_opentelemetry

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        logger.info("mcp_service_started")
        yield


app = FastAPI(title="jira-agent-mcp", lifespan=lifespan)

# Same ordering requirement as app/main.py: must run before the app's first ASGI message
# (its own lifespan-startup handshake), since Starlette caches its middleware stack then.
configure_opentelemetry(app)

app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
