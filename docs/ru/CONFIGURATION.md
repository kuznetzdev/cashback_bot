# Справочник конфигурации (RU)

Все переменные окружения, которые читает приложение, со значениями по
умолчанию, диапазонами и контекстом «когда их реально надо менять».

Все настройки объявлены в `app/bootstrap/config.py::Settings` (Pydantic v2).
Env-значения резолвятся в таком порядке (позже — важнее):

1. Дефолты Pydantic.
2. `.env` в корне проекта.
3. Process env (`export FOO=bar`, Docker `environment:`, Kubernetes
   `env:` / `envFrom:`).

`case_sensitive=False` — `BOT_TOKEN` и `bot_token` эквивалентны.
`extra="ignore"` — незнакомые переменные игнорируются.

Для полной версии на английском с детальными комментариями см.
[`docs/CONFIGURATION.md`](../CONFIGURATION.md).

---

## Оглавление

- [Telegram](#telegram)
- [Web](#web)
- [База данных](#база-данных)
- [OCR](#ocr)
- [FSM и Webhook](#fsm-и-webhook)
- [Безопасность и наблюдаемость](#безопасность-и-наблюдаемость)
- [Runtime-флаги](#runtime-флаги)
- [Таймауты и ретраи](#таймауты-и-ретраи)
- [Локализация и прочее](#локализация-и-прочее)
- [Типовые профили](#типовые-профили)

---

## Telegram

### `BOT_TOKEN`

- **Default:** `123456:TEST_TOKEN` (placeholder).
- **Обязательно при:** `APP_ENABLE_TELEGRAM=true` **или**
  `APP_ENABLE_WEB=true` с `WEB_ENABLE_TELEGRAM_AUTH=true`.
- **Валидация:** `_validate_startup_settings` отвергает placeholder,
  любой токен с подстрокой `replace_me`, и токены, оканчивающиеся на
  `:TEST_TOKEN`.
- **Пример:** `8123456789:AAH5T7_aIXXXXXXXXXXXXXXXXXX`.
- **Источник:** [@BotFather](https://t.me/BotFather).

### `TELEGRAM_BOT_USERNAME`

- **Default:** `""`.
- **Обязательно при:** `APP_ENABLE_WEB=true` (для Telegram Login widget).
- **Пример:** `cashback_analyzer_bot` (без `@`).

### `TELEGRAM_RETRY_DELAY`

- **Default:** `5.0` с.
- **Range:** `1.0` – `60.0`.
- Polling retry backoff на transient ошибки
  (`TelegramNetworkError`, `TelegramServerError`). Держите на дефолте.

---

## Web

### `APP_ENABLE_WEB`

- **Default:** `false`.
- Включает FastAPI-адаптер — SSR-приложение, `/api/best`, `/health`,
  `/metrics`, `/bot/webhook`.

### `WEB_HOST` / `WEB_PORT`

- **Default:** `0.0.0.0` / `8080`.
- Меняйте при необходимости bind'а на конкретный интерфейс или конфликте
  портов.

### `WEB_BASE_URL`

- **Default:** `http://localhost:8080`.
- Используется для Telegram Login redirect и webhook URL
  (`${WEB_BASE_URL}${WEBHOOK_PATH}`).
- Должен совпадать с публичным URL за reverse-proxy. Trailing slash
  отрезается.

### `WEB_SESSION_SECRET`

- **Default:** `change-me-session-secret` (placeholder).
- **Обязательно при:** `APP_ENABLE_WEB=true`.
- **Валидация:** model validator бросает `ValueError` на
  `Settings()`-конструкции при `APP_ENABLE_WEB=true` и placeholder.
- **Генерация:** `openssl rand -hex 32`.
- **Ротация:** invalidates все текущие сессии — пользователи логинятся
  заново.

### `WEB_SECURE_COOKIES`

- **Default:** `false`.
- **Prod:** `true` (за HTTPS).

### `WEB_MAX_UPLOAD_SIZE`

- **Default:** `5242880` (5 МиБ).
- Верхняя граница body на `/app/upload`. Реальный cap для OCR —
  `min(WEB_MAX_UPLOAD_SIZE, MAX_FILE_SIZE)`.

### `WEB_ENABLE_TELEGRAM_AUTH`

- **Default:** `true`.
- При `false` — `/auth/telegram/callback` редиректит на `/`, Telegram
  Login скрыт. Local-credentials-only mode.

---

## База данных

### `DATABASE_URL`

- **Default:** `None`.
- **Пример:** `postgresql+asyncpg://user:pass@host:5432/dbname`.
- **Приоритет над** `POSTGRES_*`.

### `POSTGRES_HOST / POSTGRES_PORT / POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD`

Стандартные параметры подключения. Дефолты — `localhost:5432`,
`cashback_bot`, `cashback_user`, `cashback_password`. **В prod менять.**

### `POSTGRES_ADMIN_DB`

- **Default:** `postgres`.
- Maintenance DB для `CREATE DATABASE` при `AUTO_CREATE_DB=true`.

### `AUTO_CREATE_DB` / `AUTO_MIGRATE`

- **Default:** `true` / `true`.
- Автосоздание БД и автомиграции на старте.
- `AUTO_MIGRATE=false` — когда ops-pipeline сам делает миграции.

### Пул

| Variable | Default | Range | Смысл |
|---|---|---|---|
| `DB_POOL_SIZE` | `10` | `1` – `200` | База пула |
| `DB_MAX_OVERFLOW` | `20` | `0` – `200` | Overflow на пики |
| `DB_POOL_TIMEOUT` | `30` | `1` – `300` | Секунды ожидания соединения |
| `DB_POOL_RECYCLE` | `300` | `30` – `3600` | Секунды до recycle |

`DB_POOL_SIZE × replicas + DB_MAX_OVERFLOW × replicas` — ниже Postgres
`max_connections` минус ~20 (admin/monitoring).

### Readiness

| Variable | Default | Range | Смысл |
|---|---|---|---|
| `DB_CONNECT_MAX_ATTEMPTS` | `20` | `1` – `120` | Бюджет retry на старте |
| `DB_CONNECT_RETRY_DELAY` | `2.0` | `0.1` – `30.0` | Секунды между попытками |
| `MIGRATION_MAX_ATTEMPTS` | `10` | `1` – `120` | Alembic retry |
| `MIGRATION_RETRY_DELAY` | `2.0` | `0.1` – `30.0` | Секунды между retries |

---

## OCR

### `OCR_PROVIDER`

- **Default:** `auto`.
- **Values:** `auto` / `tesseract` / `openai`.
- `auto`: Tesseract первым, OpenAI — только на empty/timeout.

### `OPENAI_API_KEY`

- **Default:** `""`.
- Нужен для `openai` и fallback в `auto`.

### `OPENAI_BASE_URL`

- **Default:** `""` (реальный OpenAI).
- Override для совместимых шлюзов (ProxyAPI, VSEgpt, Ollama, LM Studio…).

### `OPENAI_MODEL`

- **Default:** `gpt-4o`.
- Нужна vision-совместимая модель.

### `OPENAI_VISION_TIMEOUT` / `OPENAI_VISION_MAX_TOKENS`

- **Defaults:** `60` с / `1024` токенов.
- **Ranges:** `5` – `180` / `256` – `16000`.

### `TESSERACT_PATH`

- **Default:** `tesseract`.
- Абсолютный путь, если бинарь не в `$PATH`. Windows:
  `C:\Program Files\Tesseract-OCR\tesseract.exe`.

### `OCR_TIMEOUT`

- **Default:** `20` с.
- **Range:** `1` – `180`.

### `MAX_FILE_SIZE`

- **Default:** `5242880` (5 МиБ).
- Общий cap — Telegram фото и web upload используют.

### `TEMP_DIR`

- **Default:** `ocr_tmp`.
- Директория для OCR intermediate files. Авто-создаётся.

---

## FSM и Webhook

### `FSM_STORAGE`

- **Default:** `memory`.
- `memory`: быстро, без зависимостей, теряется на рестарте.
- `redis`: переживает рестарты, нужен `REDIS_URL`.

### `REDIS_URL`

- **Default:** `""`.
- **Обязательно при:** `FSM_STORAGE=redis` (иначе graceful fallback в
  память с warning'ом).
- **Пример:** `redis://redis:6379/0`, `rediss://host:6380/0` (TLS).
- **Префикс ключей:** `cashback_fsm:`.

### `WEBHOOK_ENABLED`

- **Default:** `false`.
- **Prerequisites:** `APP_ENABLE_TELEGRAM=true` и `APP_ENABLE_WEB=true`.

### `WEBHOOK_PATH`

- **Default:** `/bot/webhook`.

### `WEBHOOK_SECRET`

- **Default:** `""`.
- Пусто → handler не проверяет заголовок. **В prod не ставить так.**
- **Генерация:** `openssl rand -hex 32`.
- Telegram ограничивает 1–256 символов, `[A-Za-z0-9_-]`.

---

## Безопасность и наблюдаемость

### `CORS_ORIGINS`

- **Default:** `["*"]`.
- Поддерживаются и comma-separated (`a.com,b.com`), и JSON-списки
  (`["a.com","b.com"]`).
- **Prod:** сужать до конкретных origin'ов.

### `METRICS_TOKEN`

- **Default:** `""`.
- Пусто → `/metrics` открыт.
- **Генерация:** `openssl rand -hex 32`.

### `API_RATE_LIMIT_PER_MINUTE`

- **Default:** `60`.
- **Range:** `1` – `10000`.
- Per-IP token bucket на `/api/*`. In-process — для multi-replica
  добавьте edge-лимитер.

### `LOG_LEVEL`

- **Default:** `INFO`.
- `DEBUG` → цветной `ConsoleRenderer`, остальное → JSON.

---

## Runtime-флаги

### `APP_ENABLE_TELEGRAM` / `APP_ENABLE_WEB`

- **Defaults:** `true` / `false`.
- Runtime отказывается стартовать, если оба `false`.

---

## Таймауты и ретраи

| Variable | Default | Назначение |
|---|---|---|
| `OCR_TIMEOUT` | `20` с | Tesseract на изображение |
| `OPENAI_VISION_TIMEOUT` | `60` с | OpenAI на изображение |
| `DB_CONNECT_MAX_ATTEMPTS` | `20` | Readiness БД на старте |
| `DB_CONNECT_RETRY_DELAY` | `2.0` с | Между попытками |
| `DB_POOL_TIMEOUT` | `30` с | Ожидание пулового соединения |
| `DB_POOL_RECYCLE` | `300` с | Recycle соединения |
| `MIGRATION_MAX_ATTEMPTS` | `10` | Миграции на старте |
| `MIGRATION_RETRY_DELAY` | `2.0` с | Между retry миграций |
| `TELEGRAM_RETRY_DELAY` | `5.0` с | Polling backoff |

---

## Локализация и прочее

### `LANG_DEFAULT`

- **Default:** `ru`.
- **Values:** `ru` / `en`.
- Per-user язык сохраняется в `users.language` и перекрывает этот.

### `APP_TIMEZONE`

- **Default:** `Europe/Moscow`.
- IANA tz (`Europe/Moscow`, `UTC`, `America/New_York`, …).

### `REMINDER_HOUR`

- **Default:** `10`.
- **Range:** `0` – `23`.

---

## Типовые профили

### Локальная разработка

```env
BOT_TOKEN=<dev>
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

### Только web локально

```env
APP_ENABLE_TELEGRAM=false
APP_ENABLE_WEB=true
WEB_ENABLE_TELEGRAM_AUTH=false
WEB_SESSION_SECRET=<сгенерировать даже для локалки>
POSTGRES_HOST=localhost
LOG_LEVEL=DEBUG
```

### Docker Compose

Дефолты из поставляемого `docker-compose.yml` разумны. Переопределяйте
через env или `.env`:

```env
BOT_TOKEN=<real>
WEB_SESSION_SECRET=<openssl rand -hex 32>
OPENAI_API_KEY=<optional>
```

### Production один контейнер (polling)

```env
BOT_TOKEN=<real>
TELEGRAM_BOT_USERNAME=your_bot
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=false
FSM_STORAGE=redis
REDIS_URL=redis://redis:6379/0
POSTGRES_HOST=<managed>
POSTGRES_PASSWORD=<vault>
WEB_SESSION_SECRET=<vault>
WEB_SECURE_COOKIES=true
METRICS_TOKEN=<vault>
CORS_ORIGINS=https://your-frontend.com
LOG_LEVEL=INFO
OPENAI_API_KEY=<vault>
OCR_PROVIDER=auto
```

### Production webhook (HTTPS)

К предыдущему добавить:

```env
WEBHOOK_ENABLED=true
WEBHOOK_SECRET=<vault>
WEBHOOK_PATH=/bot/webhook
WEB_BASE_URL=https://your-domain.com
```

---

## Приоритет настроек

```
Process env (export FOO=bar)
      ↓ перекрывает
.env в корне проекта
      ↓ перекрывает
Default поля Settings (Pydantic)
```

Kubernetes `env:` / `envFrom:` / Docker `environment:` — всё это
process env. Локально выставленная `FOO=bar` в shell перекрывает ту же
переменную в `.env`.

---

## Добавление новой переменной

При добавлении новой настройки:

1. Добавить `Field(..., alias="FOO")` в `Settings`.
2. Добавить `FOO=<разумный default>` в `.env.example` с комментарием.
3. Добавить `"FOO"` в `REQUIRED_ENV_KEYS` в `tests/test_env_example.py`.
4. Для security-важных — добавить `model_validator` по аналогии с
   `WEB_SESSION_SECRET`.
