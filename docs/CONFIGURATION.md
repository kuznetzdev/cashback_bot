# Configuration Reference

Every environment variable the application reads, with its default, its
validation range, and when you actually need to change it.

All settings are declared in `app/bootstrap/config.py::Settings` (Pydantic
v2). Env values are resolved in this order (later wins):

1. Pydantic defaults on the `Settings` class.
2. Values in `.env` (placed at project root, read by Pydantic via
   `SettingsConfigDict`).
3. Process environment (`export FOO=bar`, Docker `environment:` block,
   Kubernetes `env:` / envFrom Secret).

`case_sensitive=False` — `BOT_TOKEN` and `bot_token` both work. `extra="ignore"`
— unknown variables are silently dropped, so you can park ops variables
like `AWS_REGION` in the same `.env` without tripping validation.

---

## Quick Reference by Category

- [Telegram](#telegram)
- [Web](#web)
- [Database](#database)
- [OCR](#ocr)
- [FSM & Webhook](#fsm--webhook)
- [Security & Observability](#security--observability)
- [Runtime Flags](#runtime-flags)
- [Timeouts & Retries](#timeouts--retries)
- [Localization & Misc](#localization--misc)

---

## Telegram

### `BOT_TOKEN`

- **Default:** `123456:TEST_TOKEN` (placeholder)
- **Required when:** `APP_ENABLE_TELEGRAM=true` **or** `APP_ENABLE_WEB=true` **and** `WEB_ENABLE_TELEGRAM_AUTH=true`.
- **Validation:** `_validate_startup_settings` refuses the placeholder, any token containing `"replace_me"` (case-insensitive), and any token ending with `:TEST_TOKEN`.
- **Example:** `8123456789:AAH5T7_aIXXXXXXXXXXXXXXXXXX`
- **Source:** get from [@BotFather](https://t.me/BotFather).

### `TELEGRAM_BOT_USERNAME`

- **Default:** `""`
- **Required when:** `APP_ENABLE_WEB=true` (for the Telegram Login widget
  URL).
- **Example:** `cashback_analyzer_bot` (no leading `@`).

### `TELEGRAM_RETRY_DELAY`

- **Default:** `5.0` seconds
- **Range:** `1.0` – `60.0`
- **When to change:** polling retry backoff on transient Telegram errors
  (`TelegramNetworkError`, `TelegramServerError`). Keep at default unless
  you're observing sustained network flakiness.

---

## Web

### `APP_ENABLE_WEB`

- **Default:** `false`
- **Values:** `true` / `false`
- **Effect:** enables the FastAPI adapter — SSR app, `/api/best`,
  `/health`, `/metrics`, `/bot/webhook`.

### `WEB_HOST`

- **Default:** `0.0.0.0`
- **When to change:** bind to a specific interface (e.g. `127.0.0.1`) if
  a reverse proxy on the same host is the only expected traffic source.

### `WEB_PORT`

- **Default:** `8080`
- **Range:** `1` – `65535`
- **When to change:** conflicts with another local service or your
  deployment topology mandates a different port.

### `WEB_BASE_URL`

- **Default:** `http://localhost:8080`
- **Used for:**
  - Telegram Login redirect URL.
  - Webhook URL (`${WEB_BASE_URL}${WEBHOOK_PATH}` is what `bot.set_webhook`
    sends to Telegram).
- **Must match** the public URL behind your reverse proxy. Trailing
  slashes are trimmed.

### `WEB_SESSION_SECRET`

- **Default:** `change-me-session-secret` (placeholder)
- **Required when:** `APP_ENABLE_WEB=true`.
- **Validation:** model validator raises `ValueError` at `Settings()`
  construction when `APP_ENABLE_WEB=true` and this is empty or still the
  default.
- **Generate:** `openssl rand -hex 32`.
- **Rotation:** rotating invalidates all existing sessions — users must
  log in again.

### `WEB_SECURE_COOKIES`

- **Default:** `false`
- **Production:** `true` (behind HTTPS).
- **Effect:** `SessionMiddleware(https_only=...)` — secure cookies aren't
  sent over plain HTTP.

### `WEB_MAX_UPLOAD_SIZE`

- **Default:** `5242880` (5 MiB)
- **Range:** `≥ 1024`
- **Effect:** upper bound on `/app/upload` request body size. Bodies
  beyond the limit return `errors.file_too_large`.
- **Pair with:** `MAX_FILE_SIZE` — the actual OCR cap is
  `min(WEB_MAX_UPLOAD_SIZE, MAX_FILE_SIZE)`.

### `WEB_ENABLE_TELEGRAM_AUTH`

- **Default:** `true`
- **Values:** `true` / `false`
- **Effect when `false`:** the `/auth/telegram/callback` route redirects
  to `/`, hiding the Telegram Login UI. Local-credentials-only mode.

---

## Database

### `DATABASE_URL`

- **Default:** `None`
- **Example:** `postgresql+asyncpg://user:pass@host:5432/dbname`
- **Takes precedence over** the individual `POSTGRES_*` vars. Use this
  when your deployment platform provides a single connection string.

### `POSTGRES_HOST`

- **Default:** `localhost`

### `POSTGRES_PORT`

- **Default:** `5432`

### `POSTGRES_DB`

- **Default:** `cashback_bot`
- **Note:** this DB doesn't need to exist beforehand if `AUTO_CREATE_DB=true`.

### `POSTGRES_USER`

- **Default:** `cashback_user`

### `POSTGRES_PASSWORD`

- **Default:** `cashback_password`
- **Change this in production.**

### `POSTGRES_ADMIN_DB`

- **Default:** `postgres`
- **Used for:** connecting to a maintenance DB to issue `CREATE DATABASE`
  when `AUTO_CREATE_DB=true`.

### `AUTO_CREATE_DB`

- **Default:** `true`
- **Effect:** on startup, connects to `POSTGRES_ADMIN_DB` and creates
  `POSTGRES_DB` if it doesn't exist.

### `AUTO_MIGRATE`

- **Default:** `true`
- **Effect:** runs `alembic upgrade head` on startup.
- **Set to `false`** if your ops pipeline runs migrations as a separate
  step (recommended for multi-replica deployments).

### Pool settings

| Variable | Default | Range | Meaning |
|---|---|---|---|
| `DB_POOL_SIZE` | `10` | `1` – `200` | Base pool size |
| `DB_MAX_OVERFLOW` | `20` | `0` – `200` | Extra connections allowed during spikes |
| `DB_POOL_TIMEOUT` | `30` | `1` – `300` | Seconds to wait for a free connection before raising |
| `DB_POOL_RECYCLE` | `300` | `30` – `3600` | Seconds before recycling a connection |

Multiplication rule: `DB_POOL_SIZE × replicas + DB_MAX_OVERFLOW × replicas`
should stay under your Postgres `max_connections` minus a safety margin
(~20 for admin/monitoring connections).

### Startup readiness

| Variable | Default | Range | Meaning |
|---|---|---|---|
| `DB_CONNECT_MAX_ATTEMPTS` | `20` | `1` – `120` | `SELECT 1` retry budget on startup |
| `DB_CONNECT_RETRY_DELAY` | `2.0` | `0.1` – `30.0` | Seconds between retries |
| `MIGRATION_MAX_ATTEMPTS` | `10` | `1` – `120` | Alembic retry budget |
| `MIGRATION_RETRY_DELAY` | `2.0` | `0.1` – `30.0` | Seconds between migration retries |

---

## OCR

### `OCR_PROVIDER`

- **Default:** `auto`
- **Values:** `auto` / `tesseract` / `openai`
- **`auto`:** Tesseract first; OpenAI fallback only on empty/timeout.
  Degrades to pure Tesseract if `OPENAI_API_KEY` is empty.
- **`tesseract`:** local-only, no network calls, no AI bill.
- **`openai`:** network-only, no local fallback.

### `OPENAI_API_KEY`

- **Default:** `""`
- **Required when:** `OCR_PROVIDER=openai` (validated at startup) or
  you want the `auto` fallback to work.

### `OPENAI_BASE_URL`

- **Default:** `""` (real OpenAI)
- **Example:** `https://api.proxyapi.ru/openai/v1` (ProxyAPI),
  `http://localhost:11434/v1` (Ollama), etc.

### `OPENAI_MODEL`

- **Default:** `gpt-4o`
- **Requires:** a vision-capable model at the chosen endpoint.

### `OPENAI_VISION_TIMEOUT`

- **Default:** `60` seconds
- **Range:** `5` – `180`

### `OPENAI_VISION_MAX_TOKENS`

- **Default:** `1024`
- **Range:** `256` – `16000`
- **Safety bound:** caps the model's response length. 1024 tokens fits a
  typical cashback-screenshot JSON with headroom.

### `TESSERACT_PATH`

- **Default:** `tesseract`
- **Set to absolute path** when the binary isn't on `$PATH`. Windows
  default install: `C:\Program Files\Tesseract-OCR\tesseract.exe`.

### `OCR_TIMEOUT`

- **Default:** `20` seconds
- **Range:** `1` – `180`
- **Tesseract subprocess timeout.** After this, the adapter kills the
  process and returns `errors.ocr_timeout`.

### `MAX_FILE_SIZE`

- **Default:** `5242880` (5 MiB)
- **Range:** `≥ 1024`
- **Shared cap** — used by both Telegram's photo handler and the web
  upload endpoint.

### `TEMP_DIR`

- **Default:** `ocr_tmp`
- **Effect:** directory for OCR intermediate files. Auto-created on
  startup. Useful for debugging (set to something persistent and inspect
  what Tesseract saw).

---

## FSM & Webhook

### `FSM_STORAGE`

- **Default:** `memory`
- **Values:** `memory` / `redis`
- **`memory`:** fast, zero deps, but state is lost on restart.
- **`redis`:** state survives restarts; requires `REDIS_URL`.

### `REDIS_URL`

- **Default:** `""`
- **Required when:** `FSM_STORAGE=redis` (graceful fallback to memory
  otherwise, with a warning).
- **Example:** `redis://redis:6379/0`, `redis://:<password>@host:6379/1`,
  `rediss://host:6380/0` (TLS).
- **Key prefix:** `cashback_fsm:` — safe to share a Redis with other
  applications.

### `WEBHOOK_ENABLED`

- **Default:** `false`
- **Prerequisites:** `APP_ENABLE_TELEGRAM=true` **and** `APP_ENABLE_WEB=true`.
- **Effect when `true`:** runtime registers a webhook with Telegram and
  disables polling. The FastAPI `/bot/webhook` route becomes the update
  receiver.

### `WEBHOOK_PATH`

- **Default:** `/bot/webhook`
- **Path fragment** — combined with `WEB_BASE_URL` to form the full URL
  for `bot.set_webhook()`. Change only if you want a less-discoverable
  path as a security-through-obscurity layer (the `WEBHOOK_SECRET` is
  the real security control).

### `WEBHOOK_SECRET`

- **Default:** `""`
- **Behaviour when empty:** the handler doesn't verify the header — any
  caller can POST to `/bot/webhook` and have their payload dispatched.
  **Don't ship this way in production.**
- **Behaviour when set:** the handler compares against
  `X-Telegram-Bot-Api-Secret-Token` and 403s on mismatch.
- **Generate:** `openssl rand -hex 32`.
- **Constraint:** Telegram limits the secret to 1–256 characters,
  `[A-Za-z0-9_-]`.

---

## Security & Observability

### `CORS_ORIGINS`

- **Default:** `["*"]`
- **Parsing:** comma-separated string is supported
  (`CORS_ORIGINS=https://a.com,https://b.com`) or JSON list
  (`CORS_ORIGINS=["https://a.com","https://b.com"]`).
- **Production:** narrow to exact origins. `*` + `allow_credentials=True`
  is quirky per CORS spec; some browsers refuse.

### `METRICS_TOKEN`

- **Default:** `""`
- **Behaviour when empty:** `/metrics` is open to anyone who can reach
  the web listener. Fine for local dev.
- **Behaviour when set:** requires `Authorization: Bearer <token>`.
- **Generate:** `openssl rand -hex 32`.

### `API_RATE_LIMIT_PER_MINUTE`

- **Default:** `60`
- **Range:** `1` – `10000`
- **Effect:** per-IP token bucket on `/api/*`. Burst = rate (both start
  equal to this number).
- **Multi-replica:** this limiter is in-process. For real multi-replica
  deployments, add an edge limiter (nginx, Cloudflare) and keep this as
  a safety net.

### `LOG_LEVEL`

- **Default:** `INFO`
- **Values:** `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`
  (case-insensitive).
- **Effect:** controls the log level floor AND the formatter —
  `DEBUG` gives the colourful `ConsoleRenderer`, any other level gives
  `JSONRenderer`.

---

## Runtime Flags

### `APP_ENABLE_TELEGRAM`

- **Default:** `true`
- **Effect:** starts the Telegram adapter (polling or webhook depending on
  `WEBHOOK_ENABLED`).

### `APP_ENABLE_WEB`

- **Default:** `false`
- **Effect:** starts the FastAPI adapter (SSR UI + JSON API + health /
  metrics + webhook receiver).

**Validation:** runtime refuses to start when both are `false`.

---

## Timeouts & Retries

Consolidated (some listed in their feature sections above):

| Variable | Default | Scope |
|---|---|---|
| `OCR_TIMEOUT` | `20` s | Tesseract per-image |
| `OPENAI_VISION_TIMEOUT` | `60` s | OpenAI per-image |
| `DB_CONNECT_MAX_ATTEMPTS` | `20` | Startup DB readiness |
| `DB_CONNECT_RETRY_DELAY` | `2.0` s | Between attempts |
| `DB_POOL_TIMEOUT` | `30` s | Wait for free pooled connection |
| `DB_POOL_RECYCLE` | `300` s | Connection recycle |
| `MIGRATION_MAX_ATTEMPTS` | `10` | Startup migrations |
| `MIGRATION_RETRY_DELAY` | `2.0` s | Between migration retries |
| `TELEGRAM_RETRY_DELAY` | `5.0` s | Between polling retry cycles |

---

## Localization & Misc

### `LANG_DEFAULT`

- **Default:** `ru`
- **Values:** `ru` / `en`
- **Effect:** default language for the locale resolver. Per-user language
  is persisted in `users.language` and overrides this.

### `APP_TIMEZONE`

- **Default:** `Europe/Moscow`
- **Format:** IANA tz identifier (`Europe/Moscow`, `UTC`,
  `America/New_York`, `Asia/Tokyo`, …).
- **Effect:** reminder scheduling uses this. If your users are in one
  region, set accordingly.

### `REMINDER_HOUR`

- **Default:** `10`
- **Range:** `0` – `23`
- **Effect:** local hour (in `APP_TIMEZONE`) when the monthly reminder
  task fires.

---

## Complete `.env.example`

The shipped `.env.example` documents every variable the application reads.
Keeping it in sync with `Settings` is mandatory — `tests/test_env_example.py`
fails CI when a key is missing.

When you add a new setting:

1. Add `Field(..., alias="FOO")` to `Settings`.
2. Add `FOO=<sensible-default>` to `.env.example` with a comment
   explaining when to change it.
3. Add `"FOO"` to `REQUIRED_ENV_KEYS` in `tests/test_env_example.py`.
4. If it's a security-relevant value, consider adding a
   `model_validator` like the one guarding `WEB_SESSION_SECRET`.

---

## Common Profiles

### Local development (single terminal)

```env
BOT_TOKEN=<your dev bot token>
TELEGRAM_BOT_USERNAME=your_dev_bot
POSTGRES_HOST=localhost
POSTGRES_USER=cashback_user
POSTGRES_PASSWORD=cashback_password
OCR_PROVIDER=tesseract
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=false
LOG_LEVEL=DEBUG
FSM_STORAGE=memory
```

### Web-only local

```env
APP_ENABLE_TELEGRAM=false
APP_ENABLE_WEB=true
WEB_ENABLE_TELEGRAM_AUTH=false
WEB_SESSION_SECRET=<generate one, even for local>
POSTGRES_HOST=localhost
LOG_LEVEL=DEBUG
```

### Docker Compose (development)

The shipped `docker-compose.yml` defaults are sane. Override via env or
a `.env` file picked up by compose:

```env
BOT_TOKEN=<your real token>
WEB_SESSION_SECRET=<openssl rand -hex 32>
OPENAI_API_KEY=<optional>
```

### Production single-container (polling)

```env
BOT_TOKEN=<real>
TELEGRAM_BOT_USERNAME=your_bot
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=false
FSM_STORAGE=redis
REDIS_URL=redis://redis:6379/0
POSTGRES_HOST=<managed postgres host>
POSTGRES_USER=<stronger>
POSTGRES_PASSWORD=<vault-sourced>
WEB_SESSION_SECRET=<vault-sourced>
WEB_SECURE_COOKIES=true
METRICS_TOKEN=<vault-sourced>
CORS_ORIGINS=https://your-frontend.com
LOG_LEVEL=INFO
OPENAI_API_KEY=<vault-sourced>
OCR_PROVIDER=auto
```

### Production webhook (behind HTTPS)

Append to the above:

```env
WEBHOOK_ENABLED=true
WEBHOOK_SECRET=<vault-sourced, 32 hex chars>
WEBHOOK_PATH=/bot/webhook
WEB_BASE_URL=https://your-domain.com
```

---

## Setting Precedence at a Glance

```
Process env (export FOO=bar)
      ↓ overrides
.env file in project root
      ↓ overrides
Settings field default (Pydantic)
```

Kubernetes `env:` / `envFrom:` / Docker `environment:` all land in the
process env layer. A locally-set `FOO=bar` in a shell outranks the same
variable in `.env`.
