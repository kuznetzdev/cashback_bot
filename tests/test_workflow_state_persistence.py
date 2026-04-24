from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.postgres.models import Base
from app.application.workflow.models import WorkflowState


@pytest.mark.asyncio
async def test_postgres_uow_persists_and_clears_workflow_state() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    from app.adapters.postgres.uow import build_uow_factory

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uow_factory = build_uow_factory(session_factory)

    async with uow_factory() as uow:
        user = await uow.users.create(display_name="Workflow User", default_language="ru")
        await uow.workflow_states.save_for_user(
            user.id,
            WorkflowState(
                selected_bank_name="T-Bank",
                pending_input_kind="manual_lines",
                temp_payload={"source_type": "manual"},
            ),
        )
        await uow.commit()

    async with uow_factory() as uow:
        saved = await uow.workflow_states.get_for_user(user.id)
        assert saved is not None
        assert saved.selected_bank_name == "T-Bank"
        assert saved.pending_input_kind == "manual_lines"
        await uow.workflow_states.delete_for_user(user.id)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.workflow_states.get_for_user(user.id) is None

    await engine.dispose()
