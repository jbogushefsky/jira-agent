import os

from app.config import Settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def configure_langsmith(settings: Settings) -> None:
    """LangGraph/LangChain runnables and langchain-mcp-adapters tools pick tracing up
    automatically from these env vars — no per-call wiring needed for those. Anything
    that bypasses LangChain (the raw Claude Code CLI subprocess) is wrapped separately
    with @traceable in graph/claude_cli.py.
    """
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.langchain_tracing_v2 else "false"
    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint

    if settings.langchain_tracing_v2 and not settings.langchain_api_key:
        logger.warning("langsmith_enabled_without_api_key")
