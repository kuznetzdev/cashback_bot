# Changelog

All notable changes to this project are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] — 2026-04-25

### Added

* **Pre-month reminder.** A few days before the new calendar month
  rolls over (default: 3 days, configurable via
  `PRE_MONTH_REMINDER_WINDOW_DAYS`), users with at least one saved
  bank receive a heads-up to refresh their cashback selection. The
  reminder respects the existing `REMINDER_HOUR` and self-deduplicates
  per upcoming-period key, so the daily scheduler tick can run safely.
* **Stale-data reminder.** When a user's most recent bank/item
  `updated_at` is older than `STALE_DATA_THRESHOLD_DAYS` (default 14),
  the bot nudges them with a "your data may be misleading — refresh
  to keep recommendations honest" message. One reminder per
  (user, calendar month).
* **`latest_updated_at_for_user`** added to `CashbackRepositoryPort`.
  Postgres implementation does a single `MAX(...)` over banks + items;
  in-memory test repo mirrors the semantics for unit tests.
* **`ApplicationFacade.send_all_reminders()`** runs the monthly +
  pre-month + stale-data use cases on each scheduler tick with
  per-use-case isolation (a failure in one variant doesn't drop the
  others on the same tick).
* **Two new env knobs**: `PRE_MONTH_REMINDER_WINDOW_DAYS`,
  `STALE_DATA_THRESHOLD_DAYS`. Both range-validated by Pydantic.
* **New locale strings**: `messages.reminder_upcoming_month`,
  `messages.reminder_stale_data` (RU + EN).

### Changed

* **`MetricsRegistry._seen_users` is now bounded LRU.** Capped at 50K
  distinct users (configurable via `max_tracked_users`); oldest is
  evicted when capacity is exceeded. The previous unbounded `set`
  leaked ~30 MiB per million users until process restart.
  `cashback_bot_active_users_total` now reports "distinct users in
  the recent window" — the more honest metric anyway.
* **Telegram photo handler** explicitly closes its `BytesIO` buffer
  immediately after copying the image bytes into `ImageUpload`, and
  drops the local handle to the bytes after passing to the OCR
  pipeline. Same treatment for the `/import` document handler.
  Reduces peak memory under burst load.
* **`ReminderSenderPort` Protocol** grew two methods
  (`send_upcoming_month_reminder`, `send_stale_data_reminder`).
  `TelegramReminderSender` and `NoopReminderSender` both implement
  them.
* **Reminder loop** now drives `send_all_reminders` instead of the
  monthly-only entry point.

### Migration notes

* No schema migration. Reminder dedup happens via existing
  `user_logs` rows with new action types
  (`pre_month_reminder_sent`, `stale_data_reminder_sent`).
* No env-var rename — only additions. Defaults are sane for any
  existing deployment.

### Stats

* Tests: 417 → 433 passing (16 new, 0 regressions).

---

## [1.1.0] — 2026-04-25

### Added

* **Cashback monthly limits per category.** `CashbackDraftItem` now
  carries an optional `monthly_limit: Decimal | None`. The parser
  recognises trailing `до N ₽` / `(до 3к)` / `max N` / `up to N` syntax
  in RU and EN, with thousand separators, decimal fractions, and the
  `к/k` shorthand. Pathological values (>10M ₽) are dropped to `None`
  rather than persisted. Postgres column added in Alembic
  `20260425_0004` (nullable, backward compatible).
* **`/export` command.** Telegram users can now request a JSON snapshot
  of every bank and cashback offer they own. Delivered as a chat
  attachment with a stable `schema_version`, ISO-8601 UTC timestamp,
  string-encoded Decimals for portability, and the user's display
  name / language preserved.
* **JSON import.** Sending a `*.json` document (≤1 MiB) back to the bot
  replaces the user's banks with the import payload. Replace, not merge —
  documented loudly. Skip-and-warn on bad rows (one bad percent doesn't
  lose 30 valid offers); hard caps (≤100 banks, ≤50 items per bank).
  Round-trips with `/export` are tested.
* **Circuit breaker for the OpenAI Vision adapter.** New
  `app.adapters.circuit_breaker.CircuitBreaker` (closed/open/half-open)
  trips after 5 consecutive failures, stays open for 60 s, then probes
  once. Protects the OpenAI bill and the upstream rate quota during
  429 storms / vendor outages. `CircuitOpenError` maps to
  `errors.ocr_timeout` so the composite OCR adapter still falls back
  to Tesseract.
* **Graceful Redis FSM degradation.** `ResilientFSMStorage` wraps the
  primary `RedisStorage` and falls back to `MemoryStorage` when Redis
  is unreachable. Same circuit-breaker tuning as above so a Redis blip
  doesn't translate into N retries per user update.
* **CI: ruff + pip-audit.** New `lint` job runs `ruff check` and
  `ruff format --check`. New `security` job runs `pip-audit` against
  pinned requirements with the OSV vulnerability service (warns on
  findings, doesn't block — until the team agrees on a hard policy).
  Ruff config in `ruff.toml` covers `app/` + `tests/` with conservative
  rule selection (E/W/F/I/B/UP/SIM/PT).

### Changed

* **Tighter input validation on `SaveBankDraftUseCase`.**
  * Bank-name length capped at 80 chars.
  * Items-per-bank capped at 50.
  * Percent must be `(0, 100]`. Typos like `АЗС 500%` are now rejected.
  * Bank names are trimmed of surrounding whitespace before persistence.
  * New error keys: `errors.bank_name_too_long`, `errors.too_many_items`,
    `errors.percent_out_of_range`. RU + EN locales updated.
* **Codebase-wide format/lint pass.** All of `app/` and `tests/` now
  matches `ruff format` and passes `ruff check` with the project's
  rule set. Cosmetic diff only — no behaviour changes.
* **Bot command menu** now advertises `/export`. Russian + English
  command descriptions added.

### Fixed

* `decode_callback("nav:bank:not-a-number")` test now uses
  `pytest.raises` (was a manual try/except — minor, but consistent
  with the rest of the suite).

### Migration notes

* No breaking changes. Schema migration `20260425_0004` is purely
  additive (nullable column).
* Locales: clients depending on the exact set of `errors.*` keys
  should add the three new ones — they only fire on input validation,
  so an outdated client just shows the key name.
* Settings: no env-var changes; `WEB_SESSION_SECRET` validator is now
  expressed as a single `if` (cosmetic).

### Stats

* Tests: 379 → 417 passing (38 new, 0 regressions).
* Files touched: ~50 across `app/`, `tests/`, `alembic/`, `.github/`,
  plus new `ruff.toml`, `CHANGELOG.md`.

---

## [1.0.0] — 2026-04-24

First production-stable release. Packaged the entire production-hardening
work series into a single tag.

### Added

* **Redis FSM storage** via `FSM_STORAGE=memory|redis` (state survives
  restarts, OOM-kills, and deploys).
* **Webhook mode** with `X-Telegram-Bot-Api-Secret-Token` verification
  for scalable production deployments.
* **Aiogram middleware stack:** `LoggingMiddleware` (correlation id +
  metrics), `ThrottlingMiddleware` (30/min/user), `UserContextMiddleware`.
* **In-memory caches:** LRU 2048 on `CategoryService.normalize`; 30s
  per-user TTL on `RankingSnapshotUseCase` with invalidation on writes.
* **Structured logging via structlog** with per-request correlation IDs
  propagated through `ContextVar`. JSON in production, console in dev.
* **`/health` endpoint** with live DB + Telegram + OCR probes (503 on
  degraded).
* **`/metrics` endpoint** (Prometheus format, bearer-token protected)
  with `requests_total`, `request_duration_seconds`, `ocr_calls_total`,
  `active_users_total`.
* **Bulk N+1 fix:** ranking entries fetched via a single JOIN over
  `banks × cashback_items`.
* **Typing indicator** during photo OCR (auto-refreshes every 4s).
* **`/quickadd` multi-bank batch** with rapidfuzz "did-you-mean?" hints
  and high-percent warnings.
* **Security hardening:** CORS middleware, security headers (`X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`), per-IP rate limiter on `/api/*`,
  Settings model validator that refuses default `WEB_SESSION_SECRET`
  when `APP_ENABLE_WEB=true`.
* **Comprehensive documentation:** README/README.ru (900+ lines each),
  `docs/{ARCHITECTURE,DEVELOPMENT,OPERATIONS,CONFIGURATION}.md` plus
  Russian translations.
* **GitHub Actions CI** with Python 3.11 + 3.12 matrix, Tesseract
  install, compose validation, and Docker image build.
* **OCR metrics adapter** (`MetricsOCRAdapter`) wired into the
  composite/Tesseract/OpenAI providers so `cashback_bot_ocr_calls_total`
  is actually populated.

### Stats

* Tests: 316 → 379 passing.
