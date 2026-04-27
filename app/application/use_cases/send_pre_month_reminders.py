"""Send a "the new month is around the corner" nudge.

The use case is **idempotent per (user, period)** — the period is the
upcoming month identifier (e.g. ``"2026-05"``). On any given day the use
case fires for every user when:

* today's date is within ``window_days`` of the next month's first day,
  and
* this user hasn't already been notified for the upcoming period, and
* the user has at least one bank saved (we don't pester users who never
  set up cashback data; their first interaction with the bot will create
  banks and *next* month's pre-reminder is the right moment).

Messages are localised by the :class:`ReminderSenderPort` implementation.

Why "pre-month": if the user only sees the reminder *after* the month
flips (the existing :class:`SendMonthlyRemindersUseCase`), they've
already missed days where they were spending against their old cashback
selection. A heads-up 2-3 days early is the actionable variant.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import date, datetime

from app.application.contracts.ports import ClockPort, ReminderSenderPort, UnitOfWorkPort

# Default window: send the reminder when there are <= this many days left
# in the current month. 3 covers "weekend before the rollover" without
# spamming people the moment month-end approaches.
_DEFAULT_WINDOW_DAYS = 3
_REMINDER_ACTION = "pre_month_reminder_sent"


class SendPreMonthRemindersUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        sender: ReminderSenderPort,
        clock: ClockPort,
        *,
        window_days: int = _DEFAULT_WINDOW_DAYS,
        reminder_hour: int = 10,
    ) -> None:
        if window_days <= 0:
            raise ValueError("window_days must be positive")
        if not 0 <= reminder_hour <= 23:
            raise ValueError("reminder_hour must be between 0 and 23")
        self.uow_factory = uow_factory
        self.sender = sender
        self.clock = clock
        self._window_days = window_days
        self._reminder_hour = reminder_hour

    async def execute(self, now: datetime | None = None) -> int:
        current = now or self.clock.now()
        # Only fire after the configured hour on each calendar day so the
        # reminder doesn't go out at 00:01 local time.
        if current.hour < self._reminder_hour:
            return 0
        days_until_next_month = _days_until_next_month(current.date())
        if days_until_next_month > self._window_days or days_until_next_month <= 0:
            return 0
        # Period key is the *upcoming* month (the one users should be
        # preparing for), not the current one — that way next-month rollover
        # doesn't double-fire on the same day.
        next_month = _next_month_first(current.date())
        period_key = next_month.strftime("%Y-%m")
        # Dedup window: the entire current calendar month. Pre-month
        # reminders only fire in the last few days of a month, so any
        # earlier "pre_month_reminder_sent" log entry within this same
        # calendar month necessarily targeted the same upcoming period.
        # Using a wider window than "today" tolerates wall-clock /
        # test-clock drift between log writer and use-case clock.
        log_floor = datetime(current.year, current.month, 1)

        sent_count = 0
        async with self.uow_factory() as uow:
            targets = await uow.identities.list_reminder_targets(provider="telegram")
            for target in targets:
                # Skip users with no banks yet — there's nothing for them to
                # refresh and the reminder would be confusing onboarding noise.
                banks = await uow.banks.list_for_user(target.user_id)
                if not banks:
                    continue
                existing = await uow.logs.list_action_since(target.user_id, _REMINDER_ACTION, log_floor)
                if any((entry.payload or {}).get("period") == period_key for entry in existing):
                    continue
                try:
                    await self.sender.send_upcoming_month_reminder(
                        target, days_until_next_month=days_until_next_month
                    )
                except Exception:
                    # Delivery failures (user blocked the bot, transient
                    # Telegram 5xx) shouldn't poison the rest of the loop —
                    # the reminder loop will try again tomorrow.
                    continue
                await uow.logs.add(
                    target.user_id,
                    _REMINDER_ACTION,
                    {
                        "period": period_key,
                        "days_until_next_month": days_until_next_month,
                        "provider": target.provider,
                        "destination": target.destination,
                    },
                )
                sent_count += 1
            await uow.commit()
        return sent_count


def _days_until_next_month(today: date) -> int:
    """Return the number of full calendar days from ``today`` (inclusive
    counter) until the first day of the next month. So if today is the
    30th and the month has 31 days, the answer is 1."""
    last_day = calendar.monthrange(today.year, today.month)[1]
    return last_day - today.day + 1


def _next_month_first(today: date) -> date:
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)
