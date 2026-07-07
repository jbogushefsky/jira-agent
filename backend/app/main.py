from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.rest import router as rest_router
from app.api.ws import router as ws_router
from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.observability.langsmith_setup import configure_langsmith
from app.observability.otel_setup import configure_opentelemetry
from app.poller.scheduler import start_scheduler, stop_scheduler

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_langsmith(settings)
    scheduler = start_scheduler()
    logger.info("app_started", poll_interval=settings.poll_interval_seconds)
    try:
        yield
    finally:
        stop_scheduler(scheduler)


app = FastAPI(title="jira-agent backend", lifespan=lifespan)

# Must happen before the app processes its first ASGI message (including its own lifespan
# startup handshake) — Starlette builds and caches its middleware stack on that first message,
# so instrumenting from inside lifespan() would silently never wire the instrumentation's
# middleware into the live stack.
configure_opentelemetry(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_router, prefix="/api")
app.include_router(ws_router)
