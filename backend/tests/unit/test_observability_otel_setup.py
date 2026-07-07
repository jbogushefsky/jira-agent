from fastapi import FastAPI

from app.observability import otel_setup


def test_configure_opentelemetry_instruments_app_and_engine(monkeypatch):
    instrumented_apps = []
    monkeypatch.setattr(
        otel_setup.FastAPIInstrumentor, "instrument_app", staticmethod(lambda app: instrumented_apps.append(app))
    )

    instrumented_engines = []

    class FakeSQLAlchemyInstrumentor:
        def instrument(self, engine):
            instrumented_engines.append(engine)

    monkeypatch.setattr(otel_setup, "SQLAlchemyInstrumentor", lambda: FakeSQLAlchemyInstrumentor())

    app = FastAPI()
    otel_setup.configure_opentelemetry(app)

    assert instrumented_apps == [app]
    assert instrumented_engines == [otel_setup.engine.sync_engine]


def test_configure_opentelemetry_reads_service_name_from_env(monkeypatch):
    monkeypatch.setattr(otel_setup.FastAPIInstrumentor, "instrument_app", staticmethod(lambda app: None))

    class FakeSQLAlchemyInstrumentor:
        def instrument(self, engine):
            pass

    monkeypatch.setattr(otel_setup, "SQLAlchemyInstrumentor", lambda: FakeSQLAlchemyInstrumentor())
    monkeypatch.setenv("OTEL_SERVICE_NAME", "custom-service-name")

    otel_setup.configure_opentelemetry(FastAPI())  # should not raise
