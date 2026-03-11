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
6. start enabled adapters

## Main Environment Variables

Settings source: `app/bootstrap/config.py`

### Runtime

- `LOG_LEVEL`
- `APP_TIMEZONE`
- `APP_ENABLE_WEB`
- `APP_ENABLE_TELEGRAM`
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

- `BOT_TOKEN` is required if the Telegram bot adapter is enabled
- `BOT_TOKEN` and `TELEGRAM_BOT_USERNAME` are also required when web Telegram linking/login is enabled

## Recommended Modes

### Web-first

```env
APP_ENABLE_WEB=true
APP_ENABLE_TELEGRAM=false
WEB_ENABLE_TELEGRAM_AUTH=true
```

### Telegram-only compatibility mode

```env
APP_ENABLE_WEB=false
APP_ENABLE_TELEGRAM=true
```

### Full hybrid mode

```env
APP_ENABLE_WEB=true
APP_ENABLE_TELEGRAM=true
WEB_ENABLE_TELEGRAM_AUTH=true
```

### Local web auth only

```env
APP_ENABLE_WEB=true
APP_ENABLE_TELEGRAM=false
WEB_ENABLE_TELEGRAM_AUTH=false
```

## Auth Behavior

### Web

- local register: `POST /auth/register`
- local login: `POST /auth/login`
- logout: `POST /auth/logout`
- Telegram callback/link flow: `GET /auth/telegram/callback`
- Telegram unlink: `POST /auth/telegram/unlink`

### Telegram

The bot authenticates through linked external identity lookup and can still create a user on first contact.

## Database Migration

The identity refactor introduces:

- nullable `users.telegram_user_id`
- `users.display_name`
- `user_identities`
- `local_credentials`

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
- reminder routing through linked identities
- Telegram rendering and routing
- web adapter behavior
- workflow interruption and recovery

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
