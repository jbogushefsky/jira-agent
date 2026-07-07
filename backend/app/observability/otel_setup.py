import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.db.session import engine


def configure_opentelemetry(app: FastAPI) -> None:
    """HTTP- and DB-layer tracing, exported via OTLP/gRPC to the `otel-collector` service.

    This is deliberately separate from LangSmith (langsmith_setup.py) — LangSmith already
    traces the LangGraph flow internals (every node, the Claude Code CLI subprocess calls)
    via @traceable and LangChain's own instrumentation. OpenTelemetry here covers what
    LangSmith doesn't see: the REST/WS request surface and the SQL queries behind it.
    """
    trace.set_tracer_provider(
        TracerProvider(
            resource=Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "jira-agent-backend")})
        )
    )
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317"),
                insecure=True,
            )
        )
    )
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
