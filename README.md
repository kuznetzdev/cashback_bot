# Cashback Analyzer

Cashback Analyzer is a core-first cashback category analysis platform with two delivery adapters:

- Telegram bot on `aiogram 3`
- Web application on `FastAPI` + SSR mobile-first UI

The product stores and compares current cashback offers from user banks/cards. It does not track transactions, accrued cashback, expenses, or budgeting.

## Documentation Map

- [Russian README](README.ru.md)
- [Product Overview](docs/PRODUCT_OVERVIEW.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development And Runbook](docs/DEVELOPMENT.md)
- [User Flows](docs/USER_FLOWS.md)
- [Web User Cases](docs/WEB_USER_CASES.md)
- [Repository Integrity Audit (historical snapshot)](docs/audits/repository-integrity-audit.md)

## Short Description

The project is a cross-platform cashback management application. It helps users collect cashback data from cards across different banks, verify and edit it, and then receive a practical recommendation on which card to use for a specific category.

## Business Goal

The system exists to help a user decide which card to pay with in a real purchase scenario.

This is not a bookkeeping product. It is a decision-support product for cashback optimization:

- collect cashback offers from different banks
- normalize them into a comparable model
- let the user verify and edit the data
- provide a practical recommendation for a category or purchase context

The broader product direction is documented in [docs/PRODUCT_OVERVIEW.md](docs/PRODUCT_OVERVIEW.md). Current implementation scope is narrower than the long-term product vision.

## What The System Does

- Authenticates Telegram identities through the shared external-identity flow.
- Supports local web registration and login.
- Collects cashback categories from screenshots via OCR.
- Accepts screenshots directly from the web home screen and routes parsed categories into bank attachment flow.
- Accepts manual category input and template-based draft creation.
- Normalizes categories across RU/EN synonyms.
- Lets the user edit draft and saved bank data.
- Stores cashback categories as month-aware snapshots so previous/current/next month can be managed separately.
- Builds category leaders, global bank ranking, and best-bank answers.
- Stores action history in `user_logs`.
- Sends monthly reminders to users with enabled notifications.
- Owns monthly reminder scheduling at the application runtime level instead of nesting it under Telegram polling lifecycle.
- Runs Telegram and web adapters independently through feature flags.

## Current Baseline Vs Product Vision

Current baseline already supports:

- OCR/manual/template data ingestion
- direct screenshot upload from the web home screen
- automatic attach-to-bank flow after OCR/manual parsing
- month-aware cashback snapshots
- draft preview and editing
- saved bank editing
- category ranking and best-match lookup
- settings, reminders, history
- local web auth and Telegram identity linking
- web and Telegram adapters over the same application core

Target product vision additionally includes future extensions such as:

- card-level metadata
- cashback limits and validity windows
- more advanced decision ranking
- richer desktop analytics and bulk editing

## Architecture Summary

The project follows a core-first split:

- `app/domain`: pure domain models, errors, enums, normalization, parsing, ranking
- `app/application`: auth use cases, business use cases, workflow contracts, workflow handlers, presenters, facade
- `app/adapters`: PostgreSQL, OCR, auth adapters, Telegram, web, scheduler, system
- `app/bootstrap`: configuration, dependency wiring, startup checks, migrations, runtime

Transport-neutral workflow entrypoint:

```python
handle_command(user, workflow_state, user_command) -> WorkflowResult
```

Current workflow structure:

- `app/application/workflow`: dispatcher, interrupt policy, draft flow, bank flow, navigation, text intents
- `app/application/presenters`: `Screen` builders and formatting helpers

Detailed architectural behavior is described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository Layout

```text
app/
  adapters/
    auth_local/
    auth_telegram/
    ocr_tesseract/
    postgres/
    scheduler/
    system/
    telegram/
    web/
  application/
    auth/
    contracts/
    dto/
    presenters/
    use_cases/
    workflow/
  bootstrap/
  domain/
  i18n/
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

Add the Telegram adapter and reminder-delivery owner with:

```bash
docker compose --profile telegram up --build
```

At startup the application can:

- create the PostgreSQL database if `AUTO_CREATE_DB=true`
- apply Alembic migrations if `AUTO_MIGRATE=true`
- launch the web adapter by default and the Telegram adapter when the `telegram` compose profile is enabled

## Required Environment

Core variables are documented in [.env.example](.env.example). The most important ones are:

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
- `APP_ENABLE_TELEGRAM`
- `APP_ENABLE_WEB`
- `WEB_ENABLE_TELEGRAM_AUTH`
- `REMINDER_DELIVERY_PROVIDER`
- `WEB_BASE_URL`
- `WEB_SESSION_SECRET`

Important nuance:

- code defaults and `.env.example` now align on a web-first local posture:
  - `APP_ENABLE_TELEGRAM=false`
  - `APP_ENABLE_WEB=true`
  - `WEB_ENABLE_TELEGRAM_AUTH=false`
  - `REMINDER_DELIVERY_PROVIDER=`
- `BOT_TOKEN` is required only when the Telegram adapter, web Telegram auth, or Telegram reminder delivery is enabled
- `TELEGRAM_BOT_USERNAME` is required only for web Telegram auth

## Run Modes

- Default local web-first: `APP_ENABLE_TELEGRAM=false`, `APP_ENABLE_WEB=true`, `WEB_ENABLE_TELEGRAM_AUTH=false`, `REMINDER_DELIVERY_PROVIDER=`
- Web with Telegram login/link: `APP_ENABLE_TELEGRAM=false`, `APP_ENABLE_WEB=true`, `WEB_ENABLE_TELEGRAM_AUTH=true`, `REMINDER_DELIVERY_PROVIDER=`
- Telegram only: `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=false`, `REMINDER_DELIVERY_PROVIDER=telegram`
- Single-process hybrid: `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=true`, `WEB_ENABLE_TELEGRAM_AUTH=true`, `REMINDER_DELIVERY_PROVIDER=telegram`

The same application core serves all modes.

## User Journey Summary

The intended daily journey is:

1. User logs in.
2. Sends a screenshot immediately or opens manual/template input.
3. Confirms the parsed categories and attaches them to a bank.
4. Chooses whether cashback belongs to previous, current, or next month.
5. Saves the active offer snapshot.
6. Later asks which card is best for a category.
7. Uses ranking output instead of manually comparing several bank apps.

The detailed state-by-state flow map is documented in [docs/USER_FLOWS.md](docs/USER_FLOWS.md).

## Validation

Useful checks:

```bash
pytest -q
python -m compileall app tests
docker compose config -q
```

## Current State

Current architectural state:

- platform identity model is active
- local web auth is active
- Telegram is a secondary external identity and delivery adapter
- workflow decomposition is complete for the current phase
- presentation helpers are split out of workflow orchestration

Residual technical debt is tracked in [docs/audits/repository-integrity-audit.md](docs/audits/repository-integrity-audit.md).
