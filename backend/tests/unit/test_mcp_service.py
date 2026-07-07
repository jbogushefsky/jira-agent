from contextlib import asynccontextmanager

from app.mcp_server import app as mod


def test_app_registers_expected_routes():
    paths = {getattr(route, "path", None) for route in mod.app.routes}
    assert "/mcp" in paths
    assert "/health" in paths


async def test_lifespan_runs_mcp_session_manager(monkeypatch):
    entered = {}

    class FakeSessionManager:
        def run(self):
            @asynccontextmanager
            async def _cm():
                entered["ran"] = True
                yield

            return _cm()

    fake_mcp = type("FakeMCP", (), {"session_manager": FakeSessionManager()})()
    monkeypatch.setattr(mod, "mcp", fake_mcp)

    async with mod.lifespan(mod.app):
        pass

    assert entered["ran"] is True


async def test_health_check_runs_a_query():
    from unittest.mock import AsyncMock

    fake_session = AsyncMock()

    result = await mod.health(session=fake_session)

    assert result == {"status": "ok"}
    fake_session.execute.assert_awaited_once()
