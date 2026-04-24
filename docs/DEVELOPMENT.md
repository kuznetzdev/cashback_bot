# Development Guide

This document is the runbook for contributing to `cashback_analyzer`. It
covers local setup, common development tasks, the test topology, and the
patterns you're expected to follow.

For architecture rationale see [`ARCHITECTURE.md`](ARCHITECTURE.md). For
production deployment concerns see [`OPERATIONS.md`](OPERATIONS.md). For
the full env-var reference see [`CONFIGURATION.md`](CONFIGURATION.md).

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ (3.12 recommended) | `python --version` |
| PostgreSQL | 15+ | Optional locally — SQLite-in-memory is used for tests |
| Redis | 7.x | Optional — only if you want to exercise `FSM_STORAGE=redis` locally |
| Tesseract OCR | 5.x with `rus` language pack | Windows: https://github.com/UB-Mannheim/tesseract/wiki — be sure to check the "Russian" option during install. Unix: `apt install tesseract-ocr tesseract-ocr-rus`. |
| Docker | Latest stable | Optional, for one-command stack bring-up |
| `openssl` or similar | — | For generating secrets: `openssl rand -hex 32` |

---

## Local Setup

```bash
# 1. Clone + enter
git clone <repo-url>
cd cashback_bot

# 2. Create and activate virtualenv
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Unix
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the example env
cp .env.example .env

# 5. Edit .env — at minimum:
#    - BOT_TOKEN=<your actual token>
#    - POSTGRES_* (or DATABASE_URL for SQLite)
#    - WEB_SESSION_SECRET (if APP_ENABLE_WEB=true)
#    - OPENAI_API_KEY (optional, for OCR fallback)

# 6. Run
python -m app.main
```

### First-time troubleshooting

| Symptom | Fix |
|---|---|
| `RuntimeError: BOT_TOKEN is not configured` | Set `BOT_TOKEN` in `.env` — not the placeholder `123456:TEST_TOKEN`. |
| `ValueError: WEB_SESSION_SECRET must be changed...` | `APP_ENABLE_WEB=true` forces a non-default secret. Run `openssl rand -hex 32`. |
| `connection refused` on startup | PostgreSQL isn't running or `POSTGRES_HOST` is wrong. Start Postgres locally, or `docker compose up db -d`. |
| `pytesseract.pytesseract.TesseractNotFoundError` | Tesseract binary isn't on `$PATH`. Set `TESSERACT_PATH=/full/path/to/tesseract` in `.env`. |
| OCR returns gibberish | Install the Russian language pack (`tesseract-ocr-rus` or tick "Russian" in the Windows installer). |

---

## Runtime Sequence

Driven by `app/bootstrap/runtime.py::run_app()`:

1. **Load settings.** `Settings()` reads `.env` + process env, runs field
   validators and the model validator (which fails-fast on unsafe combos
   like `APP_ENABLE_WEB=true` + default session secret).
2. **Configure logging.** structlog pipeline (JSON in prod, Console in dev).
3. **Validate startup combos.** `_validate_startup_settings` — dual
   adapter check, bot token presence, session secret, OCR provider config.
4. **Wait for the database.** Retries `SELECT 1` up to
   `DB_CONNECT_MAX_ATTEMPTS` times.
5. **Apply migrations.** `alembic upgrade head` when `AUTO_MIGRATE=true`.
6. **Assemble the DI container.** `build_core_container(settings)` →
   `build_application_facade(core, reminder_sender)`.
7. **Start enabled adapters.** Each adapter runs as an `asyncio.Task`.
8. **Wait for shutdown or failure.** First completed task (or SIGTERM)
   wins; the rest are cancelled in `finally`.

Graceful shutdown: signals install handlers that flip an `asyncio.Event`,
which `_await_until_shutdown_or_failure` is awaiting alongside the adapter
tasks.

---

## Run Modes

All four combinations of `APP_ENABLE_TELEGRAM` × `APP_ENABLE_WEB` are
supported:

### Telegram only

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=false
```

Standard bot deployment. Polling mode by default.

### Web only (with Telegram Login)

```env
APP_ENABLE_TELEGRAM=false
APP_ENABLE_WEB=true
WEB_ENABLE_TELEGRAM_AUTH=true
BOT_TOKEN=<needed for the Telegram Login widget>
```

The web app is served, users can register locally or via Telegram Login.
No polling, no webhook.

### Full hybrid (polling)

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=false
```

Both adapters running; Telegram uses polling.

### Full hybrid (webhook — production)

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=true
WEBHOOK_SECRET=<strong random>
WEB_BASE_URL=https://your-domain.com
```

Web serves `/bot/webhook`; Telegram POSTs updates there instead of being
polled. See [OPERATIONS.md#webhook-mode](OPERATIONS.md#webhook-mode).

### Local web without Telegram

```env
APP_ENABLE_TELEGRAM=false
APP_ENABLE_WEB=true
WEB_ENABLE_TELEGRAM_AUTH=false
```

Pure local auth. Useful when you just want to test the SSR flow.

---

## Common Development Tasks

### Add a new use case

The domain is already modelled; you're adding business logic.

1. **Sketch the interface.** What does the use case take, what does it
   return? Prefer a single public `execute(**kwargs)` method.
2. **Does it need a new port?** If the use case needs to read/write
   something that isn't already a `*RepositoryPort`, add a new protocol
   in `app/application/contracts/ports.py`.
3. **Write the test first.** In `tests/test_<use_case_name>.py`. Use
   `uow_factory` and `store` fixtures from `conftest.py`. Assert on
   `store.banks`, `store.logs`, etc. — not on implementation details.
4. **Add the class.** One file in `app/application/use_cases/`.
   Accept `uow_factory: Callable[[], UnitOfWorkPort]` via `__init__`.
5. **Implement the concrete persistence** in `app/adapters/postgres/repositories.py`
   if you added a new port method.
6. **Wire in the container.** `app/bootstrap/container.py` — instantiate
   and pass into the facade (or directly into the router if it doesn't
   need to be facade-exposed).
7. **Expose via facade** (if adapters need to call it) —
   `app/application/facade.py`.
8. **Invoke from a router/workflow.** Either `app/application/use_cases/handle_command.py`
   (for screen-driven flows) or directly from a command handler in
   `app/adapters/telegram/router.py` / `app/adapters/web/app.py`.

#### Tip: cache invalidation

If your use case writes data that `RankingSnapshotUseCase` reads (banks,
cashback items), call `RankingSnapshotUseCase.invalidate(user_id)` after
`uow.commit()`. Existing examples: `SaveBankDraftUseCase`,
`DeleteBankUseCase`, `DeleteCategoryUseCase`.

### Add a new locale string

1. Add `your.new.key` to **both** `app/locales/ru.json` and `app/locales/en.json`.
2. Reference as `localizer.t("your.new.key", language)`. For interpolation:
   `localizer.t("messages.hello", language, {"name": user.display_name})`.
3. Error keys: prefer the `errors.*` prefix. The Telegram router looks at
   `_OCR_RETRYABLE_KEYS` to decide whether to show a "try again" button.

Missing keys fall back silently (return the key itself), but CI doesn't
catch mismatches — keep the two catalogs in sync manually.

### Add a new transport adapter

Following the pattern established by `app/adapters/telegram` and
`app/adapters/web`:

1. **Reuse `ApplicationFacade`** as the single entry point — don't build
   a parallel facade. Pass it in via the adapter's dependencies
   dataclass.
2. **Map inbound events to `UserCommand`.** Whatever your transport's
   natural event shape is (HTTP POST body, WebSocket frame, CLI arg),
   normalize to `UserCommand(name, payload)`.
3. **Keep session state outside the core.** Use aiogram's FSM, FastAPI
   sessions, or whatever your transport provides. The application core
   accepts `WorkflowState` as an input and returns an updated one.
4. **Render `Screen` + `Action` list in transport-specific UX.**
   Telegram renders as inline keyboards; web renders as HTML; a CLI
   would render as text + `(y/n)` prompts.
5. **Don't import other adapters.** Shared helpers go in
   `app/adapters/<name>.py` (peer-level module), not inside a sibling
   adapter package.

### Extend identity providers

To add (say) Google OAuth:

1. **Provider constant.** Add `"google"` to any place that switches on
   provider (there's no enum today — grep for `"telegram"`).
2. **Verification adapter.** New module `app/adapters/auth_google/` with
   the HMAC/JWT verification logic.
3. **Use `AuthenticateExternalIdentityUseCase`.** No new use case needed —
   it already takes an `ExternalIdentityContext(provider, provider_user_id,
   provider_username, provider_display_name)`.
4. **Add web routes** in `app/adapters/web/app.py` (`/auth/google/callback`,
   etc.) and a link/unlink pair in the Settings screen.
5. **Add adapter + integration tests.**

### Add an Alembic migration

```bash
# Make your model change in app/adapters/postgres/models.py first
alembic revision --autogenerate -m "describe the change"
# Review the generated file in alembic/versions/ — autogenerate isn't perfect
alembic upgrade head    # apply locally
# Commit both the model change and the migration in one commit
```

On schema changes also check:

- Update `tests/test_postgres_adapter.py` if the schema change affects
  CRUD behaviour.
- Remember: tests use SQLite-in-memory via `Base.metadata.create_all`, so
  Postgres-only operators (JSONB, indexes on expressions) need to be
  gated by `.with_variant(...)` or the migration will fail at test time.

---

## Testing

### Quick reference

```bash
# Full suite
python -m pytest -q

# One file
python -m pytest tests/test_middleware.py -q

# One test
python -m pytest tests/test_middleware.py::test_throttling_middleware_allows_up_to_capacity -q

# With stdout/stderr visible
python -m pytest -s

# Stop at first failure
python -m pytest -x

# Verbose with names
python -m pytest -v

# Just the ones I changed (based on collected paths)
python -m pytest tests/test_foo.py tests/test_bar.py
```

### Test topology

| Layer | Speed | Dependencies | Approximate count |
|---|---|---|---|
| Domain unit | <10 ms | Pure Python | ~60 |
| Application unit | <50 ms | `InMemoryUnitOfWork` | ~120 |
| Adapter (postgres) | ~300 ms | `sqlite+aiosqlite` via `StaticPool` | ~15 |
| Web | ~500 ms | `httpx.AsyncClient` + `ASGITransport` | ~40 |
| Telegram router | ~200 ms | `MagicMock` bot, real router | ~20 |
| Architecture boundary | <50 ms | AST walk | ~5 |
| Scenario regressions | ~500 ms | Full facade + in-memory UoW | ~20 |

**Baseline:** 372 tests, full suite ~1–2 min on Windows, ~40 s on Unix.

### Fixtures of note (`tests/conftest.py`)

| Fixture | What it gives you |
|---|---|
| `store` | `InMemoryStore` dataclass — assert on it directly to verify persistence |
| `uow_factory` | Zero-arg callable returning a fresh `InMemoryUnitOfWork` bound to `store` |
| `dummy_ocr` | `DummyOCR` instance with a `value` attribute you can set before the test |

Use it:

```python
@pytest.mark.asyncio
async def test_save_bank_writes_items(uow_factory, store):
    use_case = SaveBankDraftUseCase(uow_factory)
    await use_case.execute(
        user_id=1, bank_id=None, bank_name="Tinkoff",
        items=[CashbackDraftItem(raw_category="АЗС", normalized_category="fuel",
                                  percent=Decimal("5"), source_type="manual")],
    )
    assert len(store.banks) == 1
    assert store.banks[1].bank_name == "Tinkoff"
```

### What CI should run

```bash
python -m pytest -q                    # all tests
python -m compileall app tests         # syntax sanity
docker compose config -q               # compose syntax
```

These three commands are the contract: if all three are green locally, CI
should pass.

### Writing tests for Web adapter

Use `httpx.AsyncClient` with `ASGITransport` — no need to actually bind
a port:

```python
from httpx import ASGITransport, AsyncClient
from app.adapters.web.app import WebDependencies, create_web_app

@pytest.mark.asyncio
async def test_health_returns_json(localizer):
    deps = WebDependencies(..., db_ping=AsyncMock(return_value=None))
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as client:
        res = await client.get("/health")
    assert res.status_code == 200
```

### Writing tests for Telegram middleware

Construct a `MagicMock` with the attributes the middleware reads
(`from_user.id`, `from_user.language_code`, `answer`) — you don't need a
real `Message`:

```python
def _fake_message(user_id=42):
    message = MagicMock(spec=[])
    from_user = MagicMock()
    from_user.id = user_id
    from_user.language_code = "ru"
    message.from_user = from_user
    message.answer = AsyncMock()
    return message
```

---

## Code Style

- **No emoji unless explicitly requested.** Log lines, docstrings, comments
  — all text stays ASCII except for user-facing locale strings.
- **Comments explain WHY, not WHAT.** Identifier names handle the "what".
  Comments exist for hidden constraints, workarounds, business context
  that would surprise a new reader.
- **No multi-paragraph docstrings on private helpers.** One line max.
- **Use `structlog.get_logger(__name__)`.** Not stdlib `logging` — the
  structlog pipeline captures stdlib logs too, but direct calls don't
  pick up bound context.
- **Pydantic v2 idioms.** `Field(default=..., alias="ENV_NAME")`,
  `model_validator(mode="after")`, `field_validator(..., mode="before")`.
  No Pydantic v1 style.
- **Type hints on every public function.** `-> SomeType:`. `from __future__
  import annotations` at the top of every file so forward refs just work.

---

## Auth Behaviour

### Web

- **`POST /auth/register`** — form fields `username`, `password`,
  optional `display_name`, `email`. Creates the user + local credentials
  in one transaction.
- **`POST /auth/login`** — form fields `username`, `password`. Starts a
  session, redirects to `/app`.
- **`POST /auth/logout`** — clears the session, redirects to `/`.
- **`GET /auth/telegram/callback`** — verifies Telegram Login HMAC. If
  the caller is already logged in, links the Telegram identity; if not,
  requires a pre-existing linked identity (refuses to silently create a
  web account from a Telegram callback).
- **`POST /auth/telegram/unlink`** — refuses when it would leave the
  account with no way to log in (no local credentials).

### Telegram

The bot authenticates through linked external identity lookup and can
still create a user on first contact (`provider="telegram"`).

---

## Database Migrations

The identity refactor introduces:

- Nullable `users.telegram_user_id` (backward compatibility).
- `users.display_name`.
- `user_identities` table — `(provider, provider_user_id)` unique.
- `local_credentials` table — user_id/username/email unique.

Run manually when needed:

```bash
alembic upgrade head
```

Migration notes: [`migrations/identity-clean-break.md`](migrations/identity-clean-break.md).

---

## Docker (for development)

```bash
# Start only the DB and Redis — run Python locally
docker compose up db redis -d

# Then run Python pointing at the containerised services
POSTGRES_HOST=localhost POSTGRES_PORT=5432 python -m app.main

# Or the whole stack
docker compose up --build -d
docker compose logs -f bot
docker compose down
```

See [OPERATIONS.md](OPERATIONS.md) for the full docker-compose topology.

---

## Failure Handling Patterns

- **Don't swallow exceptions silently.** Log with diagnosis context
  (user id, command name, relevant state) via structlog.
- **User-facing errors are short and localized.** Use
  `errors.<key>` → `localizer.t`. Never leak stack traces to the user.
- **Preserve valid workflow state after recoverable failures.** The
  router catches `DomainError` / `RuntimeError` / `OSError` separately
  so a transient OCR timeout doesn't trash the user's in-progress wizard.
- **Hard kills don't leak background tasks.** Every long-running helper
  (`_with_typing`, `ReminderLoop`) cleans up its tasks in `finally`.
- **DB failures surface as degraded `/health`.** The `_make_db_ping`
  helper times out after 2 s; Kubernetes drops the pod from rotation
  without tearing it down, so in-flight work can finish.

---

## Deployment Notes

For the full checklist see [OPERATIONS.md](OPERATIONS.md).

TL;DR:

- Generate strong `WEB_SESSION_SECRET`, `WEBHOOK_SECRET`, `METRICS_TOKEN`.
- `WEB_SECURE_COOKIES=true` behind HTTPS.
- `FSM_STORAGE=redis` in production; memory is a dev-only default.
- `AUTO_MIGRATE` is true by default — disable in environments where ops
  want manual control over schema changes.
- Monitor `/metrics`; alert on a falling `cashback_bot_active_users_total`
  or a spike in `cashback_bot_requests_total{status="error"}`.

---

## Glossary

| Term | Meaning |
|---|---|
| **UoW** | Unit of Work — a SQLAlchemy session wrapped in an async context manager exposing repository accessors. |
| **Facade** | `ApplicationFacade` — the single entry point for adapters; keeps use-case composition behind one surface. |
| **Port** | A `Protocol` class in `app/application/contracts/ports.py` — a narrow interface the application depends on. |
| **Adapter** | Concrete implementation of a port (e.g. `PostgresBankRepository` implements `BankRepositoryPort`). |
| **Screen** | A transport-neutral description of what the user sees — title, body, actions, expected input. |
| **Effect** | A side-effect request emitted by a use case (show status toast, log event). The renderer materialises it. |
| **WorkflowState** | Per-user FSM state — draft bank, current wizard step, pending input expectation. |
| **UserCommand** | Adapter-level input: `{name, payload}`. |
| **WorkflowResult** | Use-case output: `{user, state, screen, effects}`. |
| **Correlation ID** | Short uuid set per request/update, flowing through `structlog` and response headers for tracing. |
