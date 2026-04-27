"""Send a "your saved cashback data looks stale" nudge.

Many Russian banks rotate cashback categories every month. A user that
saved their offers in March and never updates is getting recommendations
based on stale data by mid-April. This use case detects that condition
and reminds the user to refresh.

Detection rules (all must hold):

* user has at least one saved bank (otherwise nothing to be stale);
* the most recent ``updated_at`` across the user's banks + items is
  older than the configured threshold (default 14 days);
* today is past the start of a fresh calendar month — staleness is
  about not having refreshed for the *current* month, not about
  not-touching-anything-ever;
* this user hasn't already received a stale-data reminder this month
  (dedup on ``"period"`` payload key in ``user_logs``).

The use case is safe to run daily; it self-deduplicates within the
month so users see at most one stale-data reminder per period.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.application.contracts.ports import ClockPort, ReminderSenderPort, UnitOfWorkPort

_DEFAULT_THRESHOLD_DAYS = 14
_REMINDER_ACTION = "stale_data_reminder_sent"


class SendStaleDataRemindersUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        sender: ReminderSenderPort,
        clock: ClockPort,
        *,
        threshold_days: int = _DEFAULT_THRESHOLD_DAYS,
        reminder_hour: int = 10,
    ) -> None:
        if threshold_days <= 0:
            raise ValueError("threshold_days must be positive")
        if not 0 <= reminder_hour <= 23:
            raise ValueError("reminder_hour must be between 0 and 23")
        self.uow_factory = uow_factory
        self.sender = sender
        self.clock = clock
        self._threshold_days = threshold_days
        self._reminder_hour = reminder_hour

    async def execute(self, now: datetime | None = None) -> int:
        current = now or self.clock.now()
        if current.hour < self._reminder_hour:
            return 0
        period_key = current.strftime("%Y-%m")
        month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        # Floor for log dedup: anything from this month's beginning. We
        # only want to send one stale-data reminder per (user, calendar
        # month) regardless of what days the breaker triggered on.
        log_floor = month_start

        sent_count = 0
        async with self.uow_factory() as uow:
            targets = await uow.identities.list_reminder_targets(provider="telegram")
            for target in targets:
                banks = await uow.banks.list_for_user(target.user_id)
                if not banks:
                    continue
                latest = await uow.cashback.latest_updated_at_for_user(target.user_id)
                if latest is None:
                    continue
                naive_now = current.replace(tzinfo=None) if current.tzinfo else current
                naive_latest = latest.replace(tzinfo=None) if latest.tzinfo else latest
                age_days = (naive_now - naive_latest).days
                if age_days < self._threshold_days:
                    continue
                existing = await uow.logs.list_action_since(target.user_id, _REMINDER_ACTION, log_floor)
                if any((entry.payload or {}).get("period") == period_key for entry in existing):
                    continue
                try:
                    await self.sender.send_stale_data_reminder(target, days_since_last_update=age_days)
                except Exception:
                    # Same rationale as the pre-month variant — bad delivery
                    # to one user must not abort the loop for everyone else.
                    continue
                await uow.logs.add(
                    target.user_id,
                    _REMINDER_ACTION,
                    {
                        "period": period_key,
                        "days_since_last_update": age_days,
                        "provider": target.provider,
                        "destination": target.destination,
                    },
                )
                sent_count += 1
            await uow.commit()
        return sent_count
