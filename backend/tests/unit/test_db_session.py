import pytest

import app.db.session as session_mod
from app.db.session import session_scope


class FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def test_get_session_yields_a_session():
    async for session in session_mod.get_session():
        assert session is not None
        break


async def test_session_scope_commits_on_success(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(session_mod, "async_session_maker", lambda: fake_session)

    async with session_scope() as session:
        assert session is fake_session

    assert fake_session.committed is True
    assert fake_session.rolled_back is False


async def test_session_scope_rolls_back_on_exception(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(session_mod, "async_session_maker", lambda: fake_session)

    with pytest.raises(ValueError):
        async with session_scope():
            raise ValueError("boom")

    assert fake_session.rolled_back is True
    assert fake_session.committed is False
