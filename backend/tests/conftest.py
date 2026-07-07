import pytest


@pytest.fixture(autouse=True)
def _disable_langsmith_tracing(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
