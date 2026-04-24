# Development And Runbook

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Tesseract OCR with Russian language pack
- Docker Desktop for compose-based startup

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

Application startup is driven by `app/bootstrap/runtime.py`.

Runtime sequence:

1. load settings
2. configure logging
3. wait for database readiness
4. run Alembic migrations when enabled
5. assemble the DI container
6. start runtime-owned reminder scheduling when a reminder delivery provider is configured
7. start enabled adapters

## Main Environment Variables

Settings source: `app/bootstrap/config.py`

### Runtime

- `LOG_LEVEL`
- `APP_TIMEZONE`
- `APP_ENABLE_WEB`
- `APP_ENABLE_TELEGRAM`
- `REMINDER_DELIVERY_PROVIDER`
- `AUTO_CREATE_DB`
- `AUTO_MIGRATE`

### Database

- `DATABASE_URL`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

### OCR

- `TESSERACT_PATH`
- `OCR_TIMEOUT`
- `MAX_FILE_SIZE`

### Web

- `WEB_HOST`
- `WEB_PORT`
- `WEB_BASE_URL`
- `WEB_SESSION_SECRET`
- `WEB_ENABLE_TELEGRAM_AUTH`

### Telegram

- `BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`

Operational note:

- code defaults and `.env.example` now align on web-first local mode
- `BOT_TOKEN` is required when the Telegram bot adapter is enabled, web Telegram linking/login is enabled, or `REMINDER_DELIVERY_PROVIDER=telegram`
- `TELEGRAM_BOT_USERNAME` is required only when web Telegram linking/login is enabled
- `WEB_SESSION_SECRET` defaults to a development-only value and must be overridden for hardened environments

## Recommended Modes

### Default local web-first

```env
APP_ENABLE_WEB=true
APP_ENABLE_TELEGRAM=false
WEB_ENABLE_TELEGRAM_AUTH=false
REMINDER_DELIVERY_PROVIDER=
```

### Web with Telegram login/link

```env
APP_ENABLE_WEB=true
APP_ENABLE_TELEGRAM=false
WEB_ENABLE_TELEGRAM_AUTH=true
REMINDER_DELIVERY_PROVIDER=
```

### Telegram-only runtime

```env
APP_ENABLE_WEB=false
APP_ENABLE_TELEGRAM=true
REMINDER_DELIVERY_PROVIDER=telegram
```

### Single-process hybrid runtime

```env
APP_ENABLE_WEB=true
APP_ENABLE_TELEGRAM=true
WEB_ENABLE_TELEGRAM_AUTH=true
REMINDER_DELIVERY_PROVIDER=telegram
```

### Reminder delivery runtime

- monthly reminder scheduling is started by `app/bootstrap/runtime.py`
- the scheduler is no longer nested under Telegram polling startup
- reminder ownership is now driven by `REMINDER_DELIVERY_PROVIDER`
- supported values are empty/disabled and `telegram`
- in multi-service compose, only one process should own reminder delivery; the bundled compose file assigns it to the Telegram profile service

## Auth Behavior

### Web

- local register: `POST /auth/register`
- local login: `POST /auth/login`
- logout: `POST /auth/logout`
- Telegram callback/link flow: `GET /auth/telegram/callback`
- Telegram unlink: `POST /auth/telegram/unlink`

### Telegram

The bot authenticates through the shared external identity use case and can still create a user on first contact.

## Workflow Architecture

Current workflow split:

- `app/application/workflow/dispatcher.py`
- `app/application/workflow/draft.py`
- `app/application/workflow/banks.py`
- `app/application/workflow/navigation.py`
- `app/application/workflow/text_intents.py`
- `app/application/workflow/interrupts.py`
- `app/application/presenters/workflow_screens.py`
- `app/application/presenters/workflow_formatters.py`

`app/application/use_cases/handle_command.py` remains only as a thin orchestration wrapper over the dispatcher.

Current user-facing behavior worth preserving in tests:

- web home screen accepts screenshot upload immediately
- Telegram accepts photos even outside the old dedicated photo state
- OCR/manual parsing drives the user into attach-to-bank flow instead of stopping after recognition
- if the user has exactly one saved bank, parsed categories auto-attach to that bank draft
- preview and saved-bank flows are month-aware (`previous`, `current`, `next`)

## Database Migration

The identity refactor introduces:

- nullable `users.telegram_user_id`
- `users.display_name`
- `user_identities`
- `local_credentials`
- `cashback_items.target_month`

Current compatibility posture after the refactor:

- legacy `users.telegram_user_id`, `username`, and `full_name` remain in schema only as deprecated compatibility fields
- new runtime writes do not mirror linked Telegram identities back into those columns

Run manually when needed:

```bash
alembic upgrade head
```

Migration notes are documented in `docs/migrations/identity-clean-break.md`.

## Docker

Start the stack with:

```bash
docker compose up --build
```

Add Telegram adapter runtime with:

```bash
docker compose --profile telegram up --build
```

Design intent:

- both adapters share one schema and one application core
- web and bot can be deployed independently
- schema migrations happen at startup when enabled

## Testing

Primary verification commands:

```bash
pytest -q
python -m compileall app tests
docker compose config -q
```

Current regression coverage includes:

- auth normalization and login flows
- external identity linking and unlinking
- repository behavior
- OCR adapter boundaries
- reminder routing through injected delivery providers over linked identities
- runtime ownership of the reminder loop outside Telegram adapter startup
- Telegram rendering and routing
- web adapter behavior
- month-aware repository behavior
- attach-after-OCR flow
- workflow interruption and recovery
- workflow decomposition boundaries

## Common Development Tasks

### Add a new business use case

1. define or extend the application port if needed
2. add a focused use case in `app/application/use_cases`
3. cover it with tests first
4. wire it in `app/bootstrap/container.py`
5. invoke it from the workflow layer or adapter

### Add a new transport adapter

1. reuse `ApplicationFacade`
2. map inbound events to `UserCommand`
3. keep adapter session state outside the core
4. render `Screen` and `Action` in transport-specific UX

### Extend identity providers

1. add a provider constant and adapter verification logic
2. persist provider + subject in `user_identities`
3. route auth through `AuthenticateExternalIdentityUseCase`
4. add adapter and integration tests

## Failure Handling

- do not swallow exceptions silently
- log operational failures with diagnosis context
- keep user-facing errors short and localized
- preserve valid workflow state after recoverable failures

## Deployment Notes

- set a strong `WEB_SESSION_SECRET`
- enable HTTPS and secure cookies in production
- keep `WEB_ENABLE_TELEGRAM_AUTH=false` if Telegram linking is not needed
- review `AUTO_MIGRATE` according to deployment policy
- monitor reminder delivery after identity migrations
