from app import main as mod


def test_app_registers_expected_routes():
    paths = {getattr(route, "path", None) for route in mod.app.routes}
    for route in mod.app.routes:
        nested_router = getattr(route, "original_router", None) or route
        nested = getattr(nested_router, "routes", None)
        if nested:
            paths.update(getattr(r, "path", None) for r in nested)
    assert "/health" in paths  # registered under rest_router, mounted at prefix="/api" in main.py
    assert "/ws/flows" in paths
    # The MCP server moved to its own service (app/mcp_server/app.py, jira-agent-mcp) —
    # it's no longer mounted in this app.
    assert "/mcp" not in paths


async def test_lifespan_starts_and_stops_scheduler(monkeypatch):
    monkeypatch.setattr(mod, "configure_langsmith", lambda settings: None)

    fake_scheduler = object()
    monkeypatch.setattr(mod, "start_scheduler", lambda: fake_scheduler)
    stopped = {}
    monkeypatch.setattr(mod, "stop_scheduler", lambda s: stopped.setdefault("scheduler", s))

    async with mod.lifespan(mod.app):
        pass

    assert stopped["scheduler"] is fake_scheduler
