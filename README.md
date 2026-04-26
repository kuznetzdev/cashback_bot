# Cashback Analyzer

Production-grade cashback category analysis platform with two delivery
adapters built on one transport-neutral application core:

- **Telegram bot** (`aiogram 3.x`) — conversational UI with inline mode and
  deep-link onboarding.
- **Web application** (`FastAPI` + SSR mobile-first UI) — local auth,
  Telegram Login linking, JSON API for scripting clients.

The product stores and compares current cashback offers from user banks and
cards. It does **not** track transactions, real accrued cashback, expenses,
or budgeting — it is a **decision-support tool** that answers the one question
that matters at the checkout: *"which card do I tap right now?"*

[![tests](https://img.shields.io/badge/tests-417%20passing-brightgreen)](tests/)
[![version](https://img.shields.io/badge/version-1.1.0-blue)](CHANGELOG.md)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![docker](https://img.shields.io/badge/docker-compose--ready-blue)](docker-compose.yml)

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Feature Highlights](#feature-highlights)
3. [Quick Start](#quick-start)
4. [Architecture At A Glance](#architecture-at-a-glance)
5. [Telegram Commands & Intents](#telegram-commands--intents)
6. [Web Endpoints](#web-endpoints)
7. [OCR Pipeline](#ocr-pipeline)
8. [FSM Storage](#fsm-storage-memory-vs-redis)
9. [Webhook Mode](#webhook-mode)
10. [Observability](#observability)
11. [Configuration](#configuration)
12. [Docker Deployment](#docker-deployment)
13. [Development Workflow](#development-workflow)
14. [Testing](#testing)
15. [Security Model](#security-model)
16. [Project Layout](#project-layout)
17. [Documentation Map](#documentation-map)
18. [Troubleshooting](#troubleshooting)

---

## What It Does

### End-user value

1. **Ingest** cashback offers from any bank via three paths:
   - **Screenshot upload** → OCR pipeline parses `Category: N%` lines.
   - **`/quickadd Tinkoff: АЗС 5%, Рестораны 3%`** → one-message bank setup.
   - **Template-based manual entry** → pre-filled categories for common
     Russian banks, edit percentages inline.
2. **Verify & edit** — preview every draft before it's saved, edit items
   after the fact.
3. **Rank & query** — "Which card for `restaurants`?" / `/best рестораны` /
   inline-mode `@your_bot фастфуд` all return the same answer.
4. **Stay current** — monthly reminders nudge the user to refresh their
   bank data before the month rolls over.

### What makes it production-ready

- **Scales horizontally** via webhook mode + Redis FSM storage (bot state
  survives deploys, OOM kills, and crashes).
- **Observable**: structured JSON logs with per-request correlation ids,
  Prometheus `/metrics`, deep `/health` probe covering DB + Telegram +
  OCR provider.
- **Hardened**: CORS, security headers, per-IP API rate limiting, bearer-token
  metrics auth, fail-fast on default secrets when the web adapter is enabled.
- **Caches aggressively**: category normalization (LRU 2 048), ranking
  snapshots (30 s per-user TTL, invalidated on writes).
- **No N+1**: ranking reads use a single JOIN over `banks × cashback_items`.
- **Layered architecture**: `domain → application → adapters`, enforced
  by boundary tests — you can't accidentally import `aiogram` from
  `app/domain` because the CI won't let you.

---

## Feature Highlights

| Area | What's there | Where |
|---|---|---|
| Multi-adapter core | Telegram + Web share `handle_command(user, state, cmd) → Screen` | `app/application/facade.py` |
| OCR tiered pipeline | Tesseract local-first, OpenAI Vision as fallback only when Tesseract returned nothing/timeout | `app/adapters/ocr_composite/` |
| Inline `@bot <query>` | Autocomplete from chat anywhere, deep-links back into the bot | `app/adapters/telegram/inline.py` |
| Multi-bank `/quickadd` | Paragraph-form input, per-block warnings with rapidfuzz "did you mean?" | `app/application/use_cases/quick_add_bank.py` |
| Category normalization | 28 slugs × RU/EN synonyms + fuzzy matcher + LRU cache | `app/domain/services/categories.py` |
| Ranking reader | 1-query JOIN + 30s per-user TTL cache | `app/adapters/postgres/repositories.py`, `app/application/use_cases/ranking_snapshot.py` |
| FSM state | MemoryStorage or RedisStorage via `FSM_STORAGE` | `app/bootstrap/runtime.py::build_fsm_storage` |
| Webhook mode | POST /bot/webhook with `X-Telegram-Bot-Api-Secret-Token` | `app/adapters/web/app.py`, `runtime.py::_run_webhook_adapter` |
| Aiogram middleware | Logging (correlation id), throttling (30/min/user), user-context injection | `app/adapters/telegram/middleware.py` |
| Web middleware | CORS, security headers, rate-limit, correlation id, Prometheus | `app/adapters/web/app.py` |
| Structured logs | structlog + JSON in prod / Console in dev + correlation ids | `app/bootstrap/logger.py` |
| Health & metrics | GET /health (503 on degraded) + GET /metrics (bearer-protected) | `app/adapters/web/app.py` |
| Reminders | Monthly via Redis-backed scheduler, only to `notifications_enabled` users | `app/adapters/scheduler/`, `app/application/use_cases/send_monthly_reminders.py` |
| i18n | `ru.json` / `en.json`, Localizer with fallback | `app/i18n/localizer.py`, `app/locales/` |
| 372 tests | Unit + architecture boundary + repository (sqlite in-memory) + web (httpx ASGI) | `tests/` |

---

## Quick Start

### 1) Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ (3.12 recommended) |
| PostgreSQL | 15+ (or SQLite for tests) |
| Tesseract OCR | 5.x, with `rus` language pack |
| Redis | 7.x (optional — only if `FSM_STORAGE=redis`) |
| Docker | Optional, compose-ready |

### 2) Local run (no Docker)

```bash
# Create and activate virtualenv
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Unix
source .venv/bin/activate

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — at minimum set BOT_TOKEN, POSTGRES_*, OPENAI_API_KEY (optional)

# Run
python -m app.main
```

On startup the runtime will:

1. Load `Settings` (Pydantic v2 from env / `.env`).
2. Configure structlog.
3. Verify the PostgreSQL database exists (create if `AUTO_CREATE_DB=true`).
4. Wait for DB readiness with retries.
5. Apply Alembic migrations (if `AUTO_MIGRATE=true`).
6. Build the dependency container.
7. Start enabled adapters (Telegram polling/webhook, web server, reminder loop).

### 3) Docker

```bash
# Copy the example env and fill in secrets
cp .env.example .env
# Edit .env — BOT_TOKEN, OPENAI_API_KEY (optional), WEB_SESSION_SECRET

# Start PostgreSQL + Redis + bot + web
docker compose up --build -d

# Tail logs
docker compose logs -f bot

# Stop
docker compose down
```

By default Docker Compose brings up:

- `db` — PostgreSQL 16 on port `5432`
- `redis` — Redis 7 on port `6379` (used by `FSM_STORAGE=redis`)
- `bot` — the Telegram adapter in polling mode
- `web` — the FastAPI adapter on port `8080`

The bot and web services share the same `Dockerfile` image; only
`APP_ENABLE_TELEGRAM` / `APP_ENABLE_WEB` differ.

### 4) Verify

```bash
# Health check (works when APP_ENABLE_WEB=true)
curl http://localhost:8080/health
# {"status":"ok","db":"ok","telegram":"ok","ocr":{...},"version":"<sha>"}

# Telegram — open your bot in Telegram and send /start
```

---

## Architecture At A Glance

### Layered core

```
┌────────────────────────────────────────────────────────────┐
│  Bootstrap  (runtime wiring, DI container, migrations)      │
├────────────────────────────────────────────────────────────┤
│  Adapters                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ telegram │  │   web    │  │ postgres │  │   ocr_*  │   │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘   │
│        │             │             │             │         │
│        └─────────────┴──────┬──────┴─────────────┘         │
├───────────────────────────── ▼ ───────────────────────────┤
│  Application  (use cases, ports, facade, workflow models)   │
├───────────────────────────── ▼ ───────────────────────────┤
│  Domain  (pure business rules: categories, ranking, parser) │
└────────────────────────────────────────────────────────────┘
```

### Layer rules (enforced by `tests/test_architecture_boundaries.py`)

| Rule | Why |
|---|---|
| `app/domain` **cannot** import `aiogram`, `fastapi`, `sqlalchemy`, or `app.adapters.*` | Domain is transport-agnostic and framework-free |
| `app/application` **cannot** import `aiogram`, `fastapi`, `sqlalchemy`, or `app.adapters.*` | Application depends on ports (protocols) only |
| `app/adapters/web` **cannot** import `app.adapters.telegram.*` | Adapters are peers, not hierarchical — shared helpers live at `app/adapters/rate_limit.py` |
| `app/application/workflow` / `presenters` **cannot** mention `UnitOfWorkPort`, `uow_factory`, `AsyncSession` | Persistence is for use cases, not workflow/presentation |

### Request lifecycle

```
Telegram update (polling or webhook)
  ↓
LoggingMiddleware sets correlation_id + starts metrics timer
  ↓
UserContextMiddleware injects tg_user_id / tg_language_code into data
  ↓
ThrottlingMiddleware checks per-user bucket (30/min default)
  ↓
Router maps update → UserCommand
  ↓
ApplicationFacade.handle_command(user, state, cmd)
  ↓
Use case (normalize category / save draft / rank / …)
  ↓
UoW (SQLAlchemy async session) via BankRepositoryPort / …
  ↓
PostgreSQL (or SQLite in tests)
  ↓
Returns Screen + Effects → Renderer → back to user
  ↓
LoggingMiddleware records latency, status → Prometheus + log
```

Web requests follow the same shape, with `_CorrelationIdMiddleware`
(X-Request-Id) replacing the Telegram middleware stack and `WebDependencies`
replacing `TelegramDependencies`.

Detailed diagrams and invariants in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Telegram Commands & Intents

The bot publishes its commands via `set_my_commands` on startup so users get
autocomplete in the attach-icon menu:

| Command | What it does |
|---|---|
| `/start` | Launch the bot. Supports deep-link payloads: `?start=inline_setup` jumps straight to "add bank"; `?start=add_bank` / `?start=top` / `?start=help` route analogously. |
| `/best <category>` | "Best card for X" answer — same path as inline mode. Empty → opens the full ranking. |
| `/quickadd Tinkoff: АЗС 5%, Рестораны 3%` | Create or replace a saved bank in one message. Supports **multi-bank batch**: separate blocks with a blank line. |
| `/banks` | Open the saved-banks list. |
| `/top` | Full ranking. Empty state → "Add first bank" onboarding CTA. |
| `/settings` | Language, notifications. |
| `/help` | List commands + common text intents. |
| `/home` | Return to the main menu. |
| `/cancel` | Discard any in-progress draft and return home. |

### Free-form text intents

Messages that aren't a slash command are routed through a text mapper:

| User typed | Maps to |
|---|---|
| "home" / "домой" | `/home` |
| "help" / "помощь" | `/help` |
| "рестораны" (any category phrase) | `/best рестораны` |
| "5% где" | Inline search fallback |

### Inline mode

`@your_bot <query>` works from any chat — users get an autocomplete list of
their best-matching categories. Tapping a result deep-links back into the bot
with the selected category pre-applied. See `app/adapters/telegram/inline.py`.

### Rate limits

| Surface | Limit | Why |
|---|---|---|
| Photo uploads (per user) | Burst 5, refill 1 / 10s | OCR is expensive — both compute and potentially a billed AI call |
| All messages / callbacks (per user) | 30 / minute (burst 30) | Global abuse cap via `ThrottlingMiddleware` |
| Inline queries | Unthrottled | Read-only; preserve autocomplete latency |
| Public `/api/*` (per IP) | `API_RATE_LIMIT_PER_MINUTE` (default 60) | Per-process token bucket — use an edge limiter for multi-replica deployments |

---

## Web Endpoints

### User-facing (HTML SSR)

| Route | Method | Description |
|---|---|---|
| `/` | GET | Landing — register / login forms and Telegram auth button |
| `/app` | GET | Authenticated app home — same Screen model as the bot |
| `/app/action` | POST | Command-like actions (buttons from the bot UX) |
| `/app/input` | POST | Text input submission |
| `/app/upload` | POST | Photo upload (routes to OCR pipeline) |
| `/auth/register`, `/auth/login`, `/auth/logout` | POST | Local auth |
| `/auth/telegram/callback` | GET | Telegram Login verification and linking |
| `/auth/telegram/unlink` | POST | Remove the linked Telegram identity |

### JSON API

| Route | Method | Auth | Description |
|---|---|---|---|
| `/api/best?q=<category>` | GET | Session | Same answer as `/best` / inline mode, returned as JSON — usable from scripting or a future mobile app |

### Operations

| Route | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | None | JSON status over DB + Telegram + OCR + version. HTTP 503 when degraded. |
| `/metrics` | GET | Bearer token (if `METRICS_TOKEN` set) | Prometheus exposition format |
| `/bot/webhook` | POST | `X-Telegram-Bot-Api-Secret-Token` | Webhook receiver (active when `WEBHOOK_ENABLED=true`) |

Response headers set by `_SecurityHeadersMiddleware`:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `X-Request-Id: <8-char uuid>` (echoed back for tracing)

---

## OCR Pipeline

Bank-app screenshots are deliberately hard to OCR — compressed text, mixed
RU/EN labels, colored badges, dark mode. The `OCR_PROVIDER` setting picks the
engine:

| Provider | Behaviour |
|---|---|
| `auto` (default) | **Local-first composite.** Tesseract runs first (free, local); OpenAI Vision is called **only** when Tesseract returned empty or timed out. If `OPENAI_API_KEY` is unset, `auto` degrades to plain Tesseract. |
| `tesseract` | Tesseract only — for fully offline deployments or hard AI-budget caps. |
| `openai` | OpenAI-compatible vision only (no local fallback). Works against any compatible endpoint: the real OpenAI, ProxyAPI, VSEgpt, self-hosted Ollama / LM Studio, Together, Groq. |

### Escalation rules for `auto`

| Error | Escalate to vision? |
|---|---|
| `errors.ocr_empty` | ✅ — Tesseract failed to read anything, AI might succeed |
| `errors.ocr_timeout` | ✅ — Tesseract hung; cut losses and call AI |
| `errors.broken_image` | ❌ — corrupt bytes, both engines would fail |
| `errors.file_too_large` | ❌ — bail before paying for the round-trip |

### Defensive parsing

The OpenAI adapter is hardened against every quirk we've seen in production:

- **Markdown-fenced responses** (```json ... ```) — stripped
- **Model chit-chat** ("Here's the JSON:\n\n{…}") — JSON extracted
- **Percentages > 100 or < 0** — clamped/dropped with `errors.ocr_parse_invalid`
- **Duplicate categories** — deduped keeping the max percentage
- **Rate-limit / auth failures** — mapped to `errors.ocr_unavailable`
- **Malformed JSON** — → `errors.ocr_parse_invalid`
- **Missing `content_type`** — defaulted to `image/jpeg`

Everything maps to the existing `errors.*` translation keys, so the UX stays
identical regardless of which engine answered.

### Typing indicator

During OCR the bot sends `chat_action=typing` on a 4-second refresh loop
(`_with_typing` in `app/adapters/telegram/router.py`) so the user doesn't see
silence for 2–10 seconds while Tesseract + AI run. The refresher task is
cancelled the moment the OCR coroutine returns or raises, guaranteeing no
leaked background tasks.

---

## FSM Storage (Memory vs Redis)

The FSM (finite-state machine) holds per-user wizard state: which step of
"add a bank" the user is on, the current draft, any pending input expectation.

| Mode | When to use | Downside |
|---|---|---|
| `FSM_STORAGE=memory` (default) | Local dev, tests, single-process throwaway setups | **Lost on every restart** — users mid-wizard get dumped to the home screen |
| `FSM_STORAGE=redis` | Production | Requires a reachable Redis (`REDIS_URL`) |

Redis keys are prefixed with `cashback_fsm:` so they can share a Redis instance
with other apps. If `FSM_STORAGE=redis` but `REDIS_URL` is empty, the runtime
logs a warning and falls back to memory — it won't refuse to start.

**Recommendation:** use Redis in production, memory anywhere else.

```env
FSM_STORAGE=redis
REDIS_URL=redis://redis:6379/0
```

---

## Webhook Mode

Polling is fine for development and small deployments but doesn't scale
horizontally — every bot replica would pull independently and Telegram doesn't
load-balance for you. In production, switch to webhook mode: Telegram POSTs
updates to your HTTPS endpoint, and the FastAPI app dispatches them through
the same aiogram Dispatcher.

### Requirements

- **Public HTTPS endpoint** resolvable by Telegram's servers.
- **`APP_ENABLE_WEB=true`** — the webhook handler lives on the FastAPI app.
- **`APP_ENABLE_TELEGRAM=true`** — you still need the bot token and
  dispatcher wiring.
- **`WEBHOOK_ENABLED=true`**.
- **`WEBHOOK_SECRET`** — a random string (~32 chars). Telegram will send it
  back in `X-Telegram-Bot-Api-Secret-Token`; the handler 403s on mismatch.

### Configuration

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=true
WEBHOOK_PATH=/bot/webhook
WEBHOOK_SECRET=<openssl rand -hex 32>
WEB_BASE_URL=https://your-domain.com
WEB_SESSION_SECRET=<another-strong-secret>
```

On startup the runtime calls `bot.set_webhook(url=f"{WEB_BASE_URL}{WEBHOOK_PATH}",
secret_token=WEBHOOK_SECRET, drop_pending_updates=True)`. On shutdown it calls
`bot.delete_webhook()` so a later polling deployment isn't left racing a stale
webhook.

### Switching back to polling

Set `WEBHOOK_ENABLED=false` (or simply skip `APP_ENABLE_WEB`). Polling mode
calls `bot.delete_webhook()` before starting, so you can flip modes without
manual API cleanup.

---

## Observability

### Structured logging

`configure_logging(level)` wires stdlib logging through structlog:

- Development (`LOG_LEVEL=DEBUG`): colourful `ConsoleRenderer`.
- Production (anything else): `JSONRenderer` → one JSON event per line, ready
  for Loki / Elasticsearch / CloudWatch / Datadog ingestion.

Every record carries a **correlation_id**:

- Telegram: set per-update by `LoggingMiddleware` (uuid4 prefix, 8 chars).
- Web: set per-request by `_CorrelationIdMiddleware` (reads `X-Request-Id`
  header or generates one; echoes back on the response).

This means one user action produces logs that can all be grepped with a
single id — across adapter, application, and repository layers.

### Prometheus metrics

Exposed on `/metrics`:

| Metric | Type | Labels | Source |
|---|---|---|---|
| `cashback_bot_requests_total` | Counter | `handler`, `status` | `LoggingMiddleware` |
| `cashback_bot_request_duration_seconds` | Histogram | `handler` | `LoggingMiddleware` |
| `cashback_bot_ocr_calls_total` | Counter | `provider`, `result` | OCR adapters (future wiring) |
| `cashback_bot_active_users_total` | Gauge | — | `LoggingMiddleware.observe_user` |

Protected with bearer-token auth when `METRICS_TOKEN` is set:

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8080/metrics
```

### Health check

`GET /health` returns:

```json
{
  "status": "ok",           // "ok" | "degraded"
  "db": "ok",               // "ok" | "error" | "n/a"
  "telegram": "ok",         // "ok" | "error" | "n/a"
  "ocr": {"primary": "auto", "status": "ok"},
  "version": "<git-sha>"
}
```

- `db` probe: `SELECT 1` with 2 s timeout.
- `telegram` probe: `bot.get_me()` with 3 s timeout (skipped when
  `APP_ENABLE_TELEGRAM=false`).
- `n/a`: probe not wired for this mode — **doesn't** trip the degraded flag.

HTTP status: `200 ok`, `503 degraded`. Use as a Kubernetes `readinessProbe` /
`livenessProbe` target.

Docker image includes `HEALTHCHECK`:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1
```

---

## Configuration

All settings go through `app/bootstrap/config.py::Settings` (Pydantic v2).
Each setting has a `Field(..., alias="ENV_NAME")` mapping so they can be
overridden via env or `.env` file.

### Required

| Env | Default | When |
|---|---|---|
| `BOT_TOKEN` | `123456:TEST_TOKEN` | Required when `APP_ENABLE_TELEGRAM=true` or web Telegram login is enabled |
| `TELEGRAM_BOT_USERNAME` | `""` | Required when `APP_ENABLE_WEB=true` (for Telegram Login widget) |
| `POSTGRES_*` or `DATABASE_URL` | `postgresql+asyncpg://cashback_user:cashback_password@localhost:5432/cashback_bot` | Any deployment using Postgres |

### Run modes

| Env | Values | Default |
|---|---|---|
| `APP_ENABLE_TELEGRAM` | `true` / `false` | `true` |
| `APP_ENABLE_WEB` | `true` / `false` | `false` |
| `WEB_ENABLE_TELEGRAM_AUTH` | `true` / `false` | `true` |

### OCR

| Env | Default | Notes |
|---|---|---|
| `OCR_PROVIDER` | `auto` | `auto` / `tesseract` / `openai` |
| `OPENAI_API_KEY` | `""` | Required for `openai`, used by `auto` fallback |
| `OPENAI_BASE_URL` | `""` | Override for OpenAI-compatible gateways |
| `OPENAI_MODEL` | `gpt-4o` | Any vision-capable model |
| `OPENAI_VISION_TIMEOUT` | `60` | Seconds |
| `OPENAI_VISION_MAX_TOKENS` | `1024` | Safety bound |
| `OCR_TIMEOUT` | `20` | Tesseract timeout in seconds |
| `MAX_FILE_SIZE` | `5242880` | 5 MiB upload cap |
| `TESSERACT_PATH` | `tesseract` | Absolute path if not on `$PATH` |

### FSM & Webhook

| Env | Default | Notes |
|---|---|---|
| `FSM_STORAGE` | `memory` | `memory` / `redis` |
| `REDIS_URL` | `""` | e.g. `redis://redis:6379/0` |
| `WEBHOOK_ENABLED` | `false` | Requires `APP_ENABLE_WEB=true` |
| `WEBHOOK_PATH` | `/bot/webhook` | Path fragment only |
| `WEBHOOK_SECRET` | `""` | Recommended — enables header verification |

### Web

| Env | Default | Notes |
|---|---|---|
| `WEB_HOST` | `0.0.0.0` | |
| `WEB_PORT` | `8080` | |
| `WEB_BASE_URL` | `http://localhost:8080` | Used for Telegram Login redirect and webhook URL |
| `WEB_SESSION_SECRET` | `change-me-session-secret` | **MUST be changed** when `APP_ENABLE_WEB=true` — Settings will refuse to construct otherwise |
| `WEB_SECURE_COOKIES` | `false` | Set to `true` behind HTTPS |
| `WEB_MAX_UPLOAD_SIZE` | `5242880` | Upper bound on `/app/upload` body size |

### Security

| Env | Default | Notes |
|---|---|---|
| `CORS_ORIGINS` | `*` | Comma-separated list; wildcard allowed in dev |
| `METRICS_TOKEN` | `""` | Empty → `/metrics` is open (dev convenience). Set in production. |
| `API_RATE_LIMIT_PER_MINUTE` | `60` | Per-IP token bucket on `/api/*` |

### Database / migrations

| Env | Default | Notes |
|---|---|---|
| `AUTO_CREATE_DB` | `true` | Creates the DB if it doesn't exist |
| `AUTO_MIGRATE` | `true` | Runs `alembic upgrade head` on startup |
| `DB_POOL_SIZE` | `10` | SQLAlchemy async pool size |
| `DB_MAX_OVERFLOW` | `20` | Overflow connections |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait for a free connection |
| `DB_POOL_RECYCLE` | `300` | Seconds before a pooled connection is recycled |
| `DB_CONNECT_MAX_ATTEMPTS` | `20` | Startup readiness retry budget |
| `DB_CONNECT_RETRY_DELAY` | `2.0` | Seconds between retries |
| `MIGRATION_MAX_ATTEMPTS` | `10` | Retry budget for Alembic |
| `MIGRATION_RETRY_DELAY` | `2.0` | Seconds between migration retries |

### Misc

| Env | Default | Notes |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` toggles console renderer |
| `LANG_DEFAULT` | `ru` | `ru` / `en` |
| `APP_TIMEZONE` | `Europe/Moscow` | Used for reminder scheduling |
| `REMINDER_HOUR` | `10` | Local hour the monthly reminder fires |
| `TELEGRAM_RETRY_DELAY` | `5.0` | Polling backoff on transient errors |
| `TEMP_DIR` | `ocr_tmp` | OCR temp files (auto-created) |

Full reference: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

---

## Docker Deployment

### docker-compose.yml layout

```yaml
services:
  db:      postgres:16-alpine, port 5432, healthcheck pg_isready
  redis:   redis:7-alpine, port 6379, healthcheck redis-cli ping
  bot:     python image (this repo), APP_ENABLE_TELEGRAM=true
  web:     python image (this repo), APP_ENABLE_WEB=true, port 8080
```

Both `bot` and `web` services:

- Depend on `db` and `redis` being healthy.
- Inherit the same image from `Dockerfile` (python:3.11-slim + tesseract).
- Run `python -m app.main` — `APP_ENABLE_*` flags gate what actually starts.
- Run as a non-root `cashback` user (UID 10001).
- Have `HEALTHCHECK CMD curl -fsS http://127.0.0.1:8080/health || exit 1`.

### Production checklist

- [ ] `BOT_TOKEN` set (real token, not placeholder)
- [ ] `TELEGRAM_BOT_USERNAME` set
- [ ] `WEB_SESSION_SECRET` regenerated (`openssl rand -hex 32`)
- [ ] `WEB_SECURE_COOKIES=true` (behind HTTPS)
- [ ] `FSM_STORAGE=redis` + `REDIS_URL` pointed at Redis
- [ ] `WEBHOOK_ENABLED=true` + `WEBHOOK_SECRET` set (if using webhook)
- [ ] `METRICS_TOKEN` set
- [ ] `CORS_ORIGINS` narrowed to the actual frontend origin(s)
- [ ] Postgres backed up on a schedule
- [ ] HTTPS reverse proxy (nginx, Caddy, Traefik) in front of the web service
- [ ] Monitoring: scrape `/metrics`, alert on `/health` non-200

Operational runbook: [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

---

## Development Workflow

### Running tests

```bash
# Full suite (all 372 tests, ~1–2 min on Windows)
python -m pytest -q

# Single file
python -m pytest tests/test_middleware.py -q

# Single test
python -m pytest tests/test_middleware.py::test_throttling_middleware_allows_up_to_capacity -q

# With output
python -m pytest -v
```

### Adding a new use case

1. **Define the port** (if it's a new persistence / transport shape) in
   `app/application/contracts/ports.py`.
2. **Add the use case** in `app/application/use_cases/` — one file, one class.
3. **Write the test first** in `tests/`. Use `uow_factory` fixture from
   `conftest.py` to get an in-memory UoW for fast unit tests.
4. **Implement the concrete adapter** in `app/adapters/postgres/` (if new
   persistence surface).
5. **Wire in the container** `app/bootstrap/container.py`.
6. **Expose via facade** `app/application/facade.py` if adapters need it.
7. **Invoke from the workflow / router** `app/application/use_cases/handle_command.py`
   or the adapter route.

### Adding a new locale string

1. Add `your.new.key` to **both** `app/locales/ru.json` and `app/locales/en.json`.
   Mismatches are fine at runtime (fallback to default), but keep them in
   sync to avoid ops surprises.
2. Reference it in code as `localizer.t("your.new.key", language)`.
3. For error keys, prefer the `errors.*` prefix — router recovery actions
   (`_OCR_RETRYABLE_KEYS`) are keyed off it.

### Running just the bot or just the web

```bash
APP_ENABLE_TELEGRAM=true APP_ENABLE_WEB=false python -m app.main
APP_ENABLE_TELEGRAM=false APP_ENABLE_WEB=true python -m app.main
```

### Alembic

```bash
# Generate a migration from model changes
alembic revision --autogenerate -m "add_new_index"

# Apply migrations
alembic upgrade head

# Downgrade one revision
alembic downgrade -1
```

Development guide: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

---

## Testing

### Test layers

| Layer | Speed | Dependencies | Count (approx) |
|---|---|---|---|
| Domain unit | <10 ms each | Pure Python | ~60 |
| Application unit | <50 ms each | In-memory UoW from `conftest.py::InMemoryUnitOfWork` | ~120 |
| Adapter (postgres) | ~300 ms each | `sqlite+aiosqlite` via `StaticPool` | ~15 |
| Web | ~500 ms each | `httpx.AsyncClient` + `ASGITransport` | ~40 |
| Telegram router | ~200 ms each | `MagicMock` bot, real router | ~20 |
| Architecture boundary | <50 ms each | AST walk | ~5 |
| Scenario regressions | ~500 ms each | Full facade wired with in-memory UoW | ~20 |

### Fixtures of note (`tests/conftest.py`)

- `store` — a bare `InMemoryStore` dataclass.
- `uow_factory` — returns a zero-arg callable that builds a new
  `InMemoryUnitOfWork` bound to the shared `store`.
- `dummy_ocr` — an OCR port stub you can configure with
  `dummy_ocr.value = "АЗС 5%"`.

### Golden-path smoke

```bash
python -m pytest -q tests/test_scenario_regressions.py
```

Scenario regression tests replay real user flows (add bank → edit percentages
→ delete item → ask best card) against the in-memory container, catching
regressions that a narrow unit test wouldn't spot.

### What CI should run

```bash
python -m pytest -q                    # all tests
python -m compileall app tests         # syntax sanity
docker compose config -q               # compose syntax
```

---

## Security Model

### Identity

- Web users can exist **without** Telegram (local credentials).
- Telegram identities can be linked to an existing account from a logged-in
  session.
- Unlinked Telegram callbacks cannot silently create a web session.
- `user_identities` stores `(provider, provider_user_id)` as a unique key.

### Passwords

- Argon2 (`argon2-cffi`), default params.
- Normalisation at input: lowercase email, trimmed username.
- Never logged, never serialized to response bodies.

### Sessions

- `SessionMiddleware` (starlette), signed with `WEB_SESSION_SECRET`.
- `max_age=14 days`, `same_site=lax`.
- `https_only=WEB_SECURE_COOKIES` (set to `true` in production).
- Settings refuses to construct when `APP_ENABLE_WEB=true` and the
  session secret is still the default placeholder.

### CSRF

- Session cookies are `same_site=lax` — most cross-site attacks fail.
- `/api/best` is GET-only and requires an authenticated session.
- Form posts on `/app/action`, `/app/input`, `/app/upload` are session-gated.

### Rate limits

See the table in [Telegram Commands & Intents](#telegram-commands--intents).

### Metrics

- `/metrics` exposes internal names. Protect with `METRICS_TOKEN` in any
  deployment that's reachable from the public internet.

### Dependencies

- `pip-audit` hasn't been wired into CI yet — it's on the roadmap. For now,
  `requirements.txt` pins major + minor version floors to trackable ranges.

---

## Project Layout

```
cashback_bot/
├── alembic/                   # DB migrations
│   └── versions/
│       ├── 20260306_0001_initial.py
│       ├── 20260311_0002_platform_identity.py
│       └── 20260424_0003_performance_indexes.py
├── app/
│   ├── main.py                # Entry point — python -m app.main
│   ├── domain/                # Pure business rules
│   │   ├── models.py          # Bank, CashbackDraftItem, UserAccount, …
│   │   ├── errors.py          # DomainError hierarchy
│   │   └── services/
│   │       ├── categories.py  # CategoryService (normalize + LRU cache)
│   │       ├── ranking.py     # RankingService
│   │       └── parsing.py     # ParserService
│   ├── application/
│   │   ├── facade.py          # ApplicationFacade — transport-neutral entry
│   │   ├── contracts/ports.py # UnitOfWorkPort, OCRPort, …
│   │   ├── dto/media.py       # ImageUpload
│   │   ├── use_cases/         # One class per use case
│   │   ├── auth/              # Registration, login, linking
│   │   ├── presenters/        # Workflow → Screen
│   │   └── models.py          # UserCommand, Screen, Action, WorkflowState
│   ├── adapters/
│   │   ├── postgres/          # SQLAlchemy async UoW + repositories
│   │   ├── telegram/          # aiogram router + middleware + renderer
│   │   ├── web/               # FastAPI app + SSR templates
│   │   ├── ocr_tesseract/     # Tesseract
│   │   ├── ocr_openai_vision/ # OpenAI-compatible vision
│   │   ├── ocr_composite/     # Local-first composite (tesseract → openai)
│   │   ├── scheduler/         # Reminder loop
│   │   ├── auth_local/        # Argon2 password hashing
│   │   ├── auth_telegram/     # Telegram Login HMAC verification
│   │   ├── system/            # Clock, reminder-sender stub
│   │   └── rate_limit.py      # Shared TokenBucketRateLimiter
│   ├── bootstrap/
│   │   ├── config.py          # Pydantic Settings
│   │   ├── container.py       # DI wiring
│   │   ├── runtime.py         # run_app() — the main event loop
│   │   ├── db_startup.py      # Auto-create DB
│   │   ├── logger.py          # structlog configuration
│   │   └── correlation.py     # correlation_id_var
│   ├── i18n/localizer.py      # Shared localizer
│   └── locales/               # ru.json, en.json
├── docs/                      # Architecture, development, operations, configs
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   ├── OPERATIONS.md
│   ├── CONFIGURATION.md
│   ├── PRODUCT_OVERVIEW.md
│   ├── USER_FLOWS.md
│   ├── WEB_USER_CASES.md
│   ├── architecture/
│   ├── audits/
│   ├── migrations/
│   └── ru/                    # Russian translations
├── tests/                     # 372 tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
├── pytest.ini
├── README.md                  # This file
└── README.ru.md               # Russian version
```

---

## Documentation Map

| Document | Purpose |
|---|---|
| [README.md](README.md) | You're reading it — TL;DR + feature tour |
| [README.ru.md](README.ru.md) | Russian translation |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, ports, invariants, runtime flow |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Dev setup, common tasks, run modes |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Deploy, webhook, monitoring, runbook |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Full env-var reference |
| [docs/PRODUCT_OVERVIEW.md](docs/PRODUCT_OVERVIEW.md) | Business domain, roadmap |
| [docs/USER_FLOWS.md](docs/USER_FLOWS.md) | Step-by-step user journeys |
| [docs/WEB_USER_CASES.md](docs/WEB_USER_CASES.md) | Web-specific use cases |
| [docs/architecture/](docs/architecture/) | Deep-dive architectural notes |
| [docs/audits/](docs/audits/) | Past audits / findings |
| [docs/migrations/](docs/migrations/) | Migration runbooks |

---

## Troubleshooting

### "Bot doesn't respond to messages"

1. Check `/health` → `telegram: ok`? If `error`, `bot.get_me()` is failing —
   almost always a bad `BOT_TOKEN`.
2. In webhook mode, hit `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`.
   `last_error_date` points to the problem (usually TLS, DNS, or 5xx).
3. In polling mode, check logs for `TelegramUnauthorizedError` (bad token) or
   repeated `TelegramNetworkError` (firewall / DNS).

### "OCR returns nothing useful"

1. Confirm `OCR_PROVIDER=auto` and `OPENAI_API_KEY` is set — Tesseract alone
   struggles with dark-theme bank screenshots.
2. Check `/metrics` → `cashback_bot_ocr_calls_total{result="error"}` rising?
3. The `errors.ocr_empty` log line carries the raw Tesseract output; grep
   for it to see what Tesseract did read.

### "Users lose their wizard state after a deploy"

You're on `FSM_STORAGE=memory`. Switch to `redis`:

```env
FSM_STORAGE=redis
REDIS_URL=redis://redis:6379/0
```

### "/metrics returns 401"

`METRICS_TOKEN` is set. Either:

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8080/metrics
```

Or unset `METRICS_TOKEN` to open it up (NOT for production).

### "Settings() raises ValueError on startup"

`APP_ENABLE_WEB=true` and `WEB_SESSION_SECRET` is still the default
`change-me-session-secret`. Generate one:

```bash
openssl rand -hex 32
# → copy into WEB_SESSION_SECRET
```

### "Rate limit fires for my own tests"

`API_RATE_LIMIT_PER_MINUTE=60` applies to `/api/*` per IP. For load tests:

```env
API_RATE_LIMIT_PER_MINUTE=10000
```

### "Telegram webhook returns 403"

The `X-Telegram-Bot-Api-Secret-Token` in the request doesn't match
`WEBHOOK_SECRET`. Re-run `bot.set_webhook(secret_token=...)` with the new
secret, or match the env variable to whatever Telegram currently uses.

---

## License & Contributing

This repository is private to the owner. Contribution policy follows the
owner's judgement; for external contributions, open an issue first describing
the change.

For feedback, issues, or feature requests — open a GitHub issue or reach out
to the repository owner directly.

---

*Generated by the `cashback_analyzer` production-hardening work series.*
*All examples and behaviours described above are backed by tests in
`tests/` and can be verified locally with `python -m pytest -q`.*
