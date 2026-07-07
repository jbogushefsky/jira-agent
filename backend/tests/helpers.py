from contextlib import asynccontextmanager
from unittest.mock import AsyncMock


def make_fake_session_scope(session=None):
    """Returns (fake_session_scope_cm_factory, session) — patch a node module's
    `session_scope` name with the factory so `async with session_scope() as session`
    yields a mock instead of hitting a real database.
    """
    session = session if session is not None else AsyncMock()

    @asynccontextmanager
    async def _scope():
        yield session

    return _scope, session
