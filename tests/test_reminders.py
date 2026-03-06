from __future__ import annotations

from datetime import datetime

import pytest

from app.infrastructure.reminders import ReminderDispatcher


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


@pytest.mark.asyncio
async def test_monthly_reminder_is_sent_only_once_per_period(app_container, session, db_user) -> None:
    dispatcher = ReminderDispatcher(app_container)
    bot = FakeBot()
    db_user.notifications_enabled = True
    await session.commit()

    current_time = datetime(2026, 3, 1, 10, 0, 0)
    await dispatcher.dispatch_due_reminders(bot, now=current_time)
    await dispatcher.dispatch_due_reminders(bot, now=current_time)

    assert len(bot.sent_messages) == 1
