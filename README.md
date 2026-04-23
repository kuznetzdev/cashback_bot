# Cashback Analyzer

Cashback Analyzer is a core-first cashback category analysis platform with two adapter layers:

- Telegram bot on `aiogram 3`
- Web application on `FastAPI` + SSR mobile-first UI

The product stores and compares current cashback offers from user banks/cards. It does not track transactions, real accrued cashback, expenses, or budgeting.

## Documentation Map

- [Русская версия README](C:\Users\Kuznetz\Desktop\proga\cashback_bot\README.ru.md)
- [Product Overview](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\PRODUCT_OVERVIEW.md)
- [Architecture](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ARCHITECTURE.md)
- [Development And Runbook](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\DEVELOPMENT.md)
- [User Flows](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\USER_FLOWS.md)
- [Web User Cases](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\WEB_USER_CASES.md)
- [Русская документация](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ru\PRODUCT_OVERVIEW.md)

## Short Description

The project is a cross-platform web application for cashback management. It helps users collect cashback data from cards across different banks, verify and edit it, and then receive clear recommendations on which card to use for a specific category in order to maximize value.

## Business Goal

The system exists to help a user decide which card to pay with in a real purchase scenario.

This is not a bookkeeping product. It is a decision-support product for cashback optimization:

- collect cashback offers from different banks
- normalize them into a comparable model
- let the user verify and edit the data
- provide a practical recommendation for a category or purchase context

In business terms, the product is a user-centric fintech utility that reduces value loss caused by fragmented bank offers, simplifies work with monthly-changing cashback categories, and converts complex banking conditions into a fast, practical, and mobile/desktop-friendly user experience.

The long-term product direction is documented in [docs/PRODUCT_OVERVIEW.md](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\PRODUCT_OVERVIEW.md). Current implementation scope is narrower than the full product vision, and the docs now separate those two layers explicitly.

## What The System Does

- Syncs Telegram users on `/start` or Telegram web login.
- Collects cashback categories from bank-app screenshots via an OpenAI-compatible vision LLM (with a Tesseract fallback).
- Accepts manual category input and template-based draft creation.
- Normalizes categories across RU/EN synonyms.
- Lets the user edit draft and saved bank data.
- Builds category leaders, global bank ranking, and best-bank answers.
- Stores action history in `user_logs`.
- Sends monthly reminders to users with enabled notifications.
- Runs Telegram and web adapters independently through feature flags.

## Current Baseline Vs Product Vision

Current baseline already supports:

- OCR/manual/template data ingestion
- draft preview and editing
- saved bank editing
- category ranking and best-match lookup
- settings, reminders, history
- web and Telegram adapters over the same application core

Target product vision additionally includes future extensions such as:

- card-level metadata
- cashback limits and validity windows
- more advanced decision ranking
- historical monthly snapshots
- richer desktop analytics and bulk editing

These future capabilities are described as roadmap/product direction, not as already-implemented features.

## Architecture Summary

The project follows a hexagonal/core-first split:

- `app/domain`: pure domain models, enums, errors, normalization, parsing helpers, ranking rules.
- `app/application`: workflow contracts, use cases, ports, application facade.
- `app/adapters`: PostgreSQL, OCR (Tesseract + OpenAI-compatible vision), Telegram, web, scheduler, system clock.
- `app/bootstrap`: configuration, dependency wiring, startup checks, migrations, runtime.

### Screenshot Recognition

Bank-app screenshots are notoriously hard for classic OCR — compressed text,
colored badges, mixed Russian/English labels. The `OCR_PROVIDER` setting picks
the engine used to turn an uploaded image into `Category: N%` lines for the
parser:

- `auto` (default, **local-first**) — when `OPENAI_API_KEY` is set, uses a
  composite adapter: **Tesseract runs first** (free, local), **OpenAI vision
  is only called if Tesseract returned empty/timeout** for that specific
  screenshot. If the API key is absent, auto is plain Tesseract. This keeps
  the AI bill small while still giving the user a second chance on the hard
  screenshots Tesseract mangles.
- `tesseract` — `app/adapters/ocr_tesseract` only. Useful for fully offline
  deployments or when an AI budget is a hard constraint.
- `openai` — `app/adapters/ocr_openai_vision` only (no Tesseract fallback).
  The adapter works against any OpenAI-compatible gateway: the real OpenAI,
  Russian proxies (ProxyAPI, VSEgpt, …), self-hosted Ollama / LM Studio,
  Together or Groq. Only `OPENAI_BASE_URL`, `OPENAI_MODEL`, and the API key
  change.

**Escalation rules for `auto`:** `errors.ocr_empty` and `errors.ocr_timeout`
trigger the AI fallback; `errors.broken_image` / `errors.file_too_large` do
not (both engines would fail equally, no point paying for the round-trip).

The adapter is defensive by design: markdown-fenced replies, model
pre-commentary, out-of-range percentages, duplicate categories, rate-limit
errors, timeouts, auth failures, malformed JSON, and missing `content_type`
headers are all mapped to the existing `errors.*` translation keys so the UX
stays the same regardless of which engine answered.

The business entrypoint is transport-agnostic:

```python
handle_command(user, workflow_state, user_command) -> WorkflowResult
```

Both Telegram and web adapters transform external input into `UserCommand` and render the returned `Screen`.

Detailed architectural behavior is described in [docs/ARCHITECTURE.md](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ARCHITECTURE.md).

## Repository Layout

```text
app/
  adapters/
    ocr_openai_vision/
    ocr_tesseract/
    postgres/
    scheduler/
    system/
    telegram/
    web/
  application/
    contracts/
    use_cases/
  bootstrap/
  domain/
  locales/
  main.py
alembic/
docs/
tests/
```

## Quick Start

### Local

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

### Docker

```bash
docker compose up --build
```

At startup the application can:

- create the PostgreSQL database if `AUTO_CREATE_DB=true`
- apply Alembic migrations if `AUTO_MIGRATE=true`
- launch Telegram and/or web adapters depending on feature flags

## Required Environment

Core variables are documented in [.env.example](C:\Users\Kuznetz\Desktop\proga\cashback_bot\.env.example). The most important ones are:

- `BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `LANG_DEFAULT`
- `OCR_TIMEOUT`
- `MAX_FILE_SIZE`
- `OCR_PROVIDER` — `auto` (default), `openai`, or `tesseract`
- `OPENAI_API_KEY` — required for `openai` or `auto` with LLM vision
- `OPENAI_BASE_URL` — override for OpenAI-compatible endpoints (ProxyAPI, VSEgpt, Ollama, LM Studio, Together, Groq). Leave empty for the real OpenAI.
- `OPENAI_MODEL` — defaults to `gpt-4o`
- `APP_ENABLE_TELEGRAM`
- `APP_ENABLE_WEB`
- `WEB_BASE_URL`
- `WEB_SESSION_SECRET`

## Run Modes

- Telegram only: `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=false`
- Web only: `APP_ENABLE_TELEGRAM=false`, `APP_ENABLE_WEB=true`
- Both adapters: `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=true`

The same application core serves all modes.

## User Journey Summary

The intended daily journey is:

1. User logs in.
2. Adds or updates a bank/card cashback offer.
3. Verifies OCR/manual parsing on preview.
4. Saves current active offers.
5. Later asks "what should I pay with for this category?"
6. Uses ranking output instead of manually comparing several bank apps.

The detailed state-by-state flow map is documented in [docs/USER_FLOWS.md](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\USER_FLOWS.md).

## Validation

Useful checks:

```bash
pytest -q
python -m compileall app
docker compose config -q
```

Current staged baseline passes these checks.
