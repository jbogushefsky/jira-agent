import os

from app.config import Settings
from app.observability.langsmith_setup import configure_langsmith


def test_configure_langsmith_sets_env_vars_when_enabled_with_key():
    settings = Settings(
        langchain_tracing_v2=True,
        langchain_api_key="key123",
        langchain_project="proj",
        langchain_endpoint="https://example.com",
    )
    configure_langsmith(settings)
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_API_KEY"] == "key123"
    assert os.environ["LANGCHAIN_PROJECT"] == "proj"
    assert os.environ["LANGCHAIN_ENDPOINT"] == "https://example.com"


def test_configure_langsmith_warns_when_tracing_enabled_without_key(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    settings = Settings(langchain_tracing_v2=True, langchain_api_key="", langchain_project="p", langchain_endpoint="e")
    configure_langsmith(settings)
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"


def test_configure_langsmith_disabled_sets_false():
    settings = Settings(langchain_tracing_v2=False, langchain_api_key="", langchain_project="p", langchain_endpoint="e")
    configure_langsmith(settings)
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
