# Development And Runbook

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Tesseract OCR with Russian language pack
- Docker Desktop for containerized startup

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

`app.main` delegates to [app/bootstrap/runtime.py](C:\Users\Kuznetz\Desktop\proga\cashback_bot\app\bootstrap\runtime.py), which performs:

1. settings load
2. logging configuration
3. optional database auto-creation
4. connection readiness wait
5. Alembic migrations
6. adapter startup

## Environment Strategy

Settings source: [app/bootstrap/config.py](C:\Users\Kuznetz\Desktop\proga\cashback_bot\app\bootstrap\config.py)

Environment categories:

- Telegram: `BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`
- Postgres: `POSTGRES_*`, optional `DATABASE_URL`
- OCR: `TESSERACT_PATH`, `OCR_TIMEOUT`, `MAX_FILE_SIZE`
- Runtime: `APP_TIMEZONE`, `LOG_LEVEL`, `TEMP_DIR`
- Web: `APP_ENABLE_WEB`, `WEB_HOST`, `WEB_PORT`, `WEB_BASE_URL`, `WEB_SESSION_SECRET`
- Bootstrap: `AUTO_CREATE_DB`, `AUTO_MIGRATE`, retry and pool settings

## Recommended Modes

### Telegram only

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=false
```

### Web only

```env
APP_ENABLE_TELEGRAM=false
APP_ENABLE_WEB=true
```

### Both

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
```

## Docker

The compose file starts:

- `db`
- `bot`
- `web`

Run:

```bash
docker compose up --build
```

Design intent:

- both adapter services share the same codebase and schema
- bot and web can be deployed separately
- database creation and migrations happen at application startup

## Testing

Primary commands:

```bash
pytest -q
python -m compileall app
docker compose config -q
```

The current suite covers:

- category normalization
- parser and intent recognition
- ranking semantics
- repository behavior
- runtime configuration
- OCR adapter guard rails
- Telegram mapping/rendering
- web adapter behavior
- workflow interruption and recovery

## Common Dev Tasks

### Add a new screen action

1. Add a new `UserCommand` usage in the relevant adapter mapping if needed.
2. Implement the behavior in `HandleCommandUseCase`.
3. Return a `Screen` and optional `Effect`.
4. Add tests at application level first.
5. Add adapter-specific tests if rendering behavior changes.

### Add a new storage-backed feature

1. Extend application ports if the core needs a new dependency.
2. Implement repository/UoW behavior in the PostgreSQL adapter.
3. Add Alembic migration.
4. Wire the dependency in `bootstrap/container.py`.

### Add a new adapter

1. Reuse `ApplicationFacade`.
2. Map inbound events to `UserCommand`.
3. Persist transport-specific workflow state outside the core.
4. Render `Screen` according to adapter UX.

## Failure Handling Expectations

- Do not swallow exceptions silently.
- Log transport and runtime failures with enough detail for diagnosis.
- Return localized and short user-facing messages.
- Keep the user in a valid flow state after recoverable errors.

## Deployment Notes

- Use a real `BOT_TOKEN`.
- Set a non-default `WEB_SESSION_SECRET` before enabling the web adapter.
- Prefer secure cookies and HTTPS in production.
- Tune DB pool settings for multi-user deployment.
- Keep `AUTO_MIGRATE=true` only if your deployment policy allows migration at boot.
