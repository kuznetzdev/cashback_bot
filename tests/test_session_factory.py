from __future__ import annotations

from app.adapters.postgres import session as session_module


def test_create_session_factory_passes_pool_parameters(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyEngine:
        pass

    def _fake_create_async_engine(database_url: str, **kwargs):
        captured["database_url"] = database_url
        captured.update(kwargs)
        return DummyEngine()

    class DummySessionFactory:
        pass

    def _fake_async_sessionmaker(engine, **kwargs):
        captured["session_engine"] = engine
        captured["session_kwargs"] = kwargs
        return DummySessionFactory()

    monkeypatch.setattr(session_module, "create_async_engine", _fake_create_async_engine)
    monkeypatch.setattr(session_module, "async_sessionmaker", _fake_async_sessionmaker)

    engine, session_factory = session_module.create_session_factory(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        pool_size=20,
        max_overflow=30,
        pool_timeout=45,
        pool_recycle=900,
    )

    assert isinstance(engine, DummyEngine)
    assert isinstance(session_factory, DummySessionFactory)
    assert captured["database_url"] == "postgresql+asyncpg://user:pass@localhost:5432/db"
    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == 20
    assert captured["max_overflow"] == 30
    assert captured["pool_timeout"] == 45
    assert captured["pool_recycle"] == 900
    session_kwargs = captured["session_kwargs"]
    assert isinstance(session_kwargs, dict)
    assert session_kwargs["expire_on_commit"] is False
