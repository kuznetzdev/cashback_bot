from __future__ import annotations

from decimal import Decimal

import pytest

from app.handlers.common import common_text_handler
from app.handlers.start import start_command
from app.schemas.cashback_item import DraftCashbackItem


class FakeRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def show_screen(self, _event, _state, text: str, reply_markup=None):
        self.calls.append(("show", text))

    async def notify_error(self, _event, text: str):
        self.calls.append(("error", text))


class FakeMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append(text)
        return self


@pytest.mark.asyncio
async def test_start_command_logs_and_renders_home(app_container, session, db_user) -> None:
    renderer = FakeRenderer()
    message = FakeMessage()

    await start_command(message, object(), session, db_user, app_container, renderer)

    assert renderer.calls
    assert "Cashback Analyzer" in renderer.calls[0][1]


@pytest.mark.asyncio
async def test_common_handler_answers_best_query(app_container, session, db_user) -> None:
    await app_container.catalog_service.save_bank(
        session,
        db_user,
        bank_name="T-Bank",
        items=[
            DraftCashbackItem(
                raw_category="АЗС",
                normalized_category="fuel",
                percent=Decimal("5"),
                source_type="manual",
            )
        ],
        source_type="manual",
    )

    message = FakeMessage("где лучше азс")
    renderer = FakeRenderer()
    await common_text_handler(message, session, db_user, app_container, renderer)

    assert message.answers
    assert "T-Bank" in message.answers[0]
