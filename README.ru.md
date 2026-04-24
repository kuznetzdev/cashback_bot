# Cashback Analyzer

Production-grade платформа анализа категорий кешбэка с двумя адаптерами
поверх единого ядра приложения:

- **Telegram-бот** (`aiogram 3.x`) — диалоговый UI с inline-режимом и
  deep-link онбордингом.
- **Веб-приложение** (`FastAPI` + SSR mobile-first UI) — локальная
  авторизация, привязка Telegram Login, JSON API для скриптовых клиентов.

Продукт хранит и сравнивает текущие предложения кешбэка по банкам и картам
пользователя. Он **не** отслеживает транзакции, фактически начисленный
кешбэк, расходы и бюджет — это **инструмент поддержки решений**, который
отвечает на один вопрос, важный на кассе: *«какой картой платить прямо
сейчас?»*.

[![tests](https://img.shields.io/badge/tests-372%20passing-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![docker](https://img.shields.io/badge/docker-compose--ready-blue)](docker-compose.yml)

---

## Оглавление

1. [Что делает система](#что-делает-система)
2. [Ключевые возможности](#ключевые-возможности)
3. [Быстрый старт](#быстрый-старт)
4. [Архитектура на пальцах](#архитектура-на-пальцах)
5. [Команды Telegram](#команды-telegram-и-текстовые-намерения)
6. [Endpoint'ы веба](#endpointы-веба)
7. [OCR-конвейер](#ocr-конвейер)
8. [FSM-хранилище](#fsm-хранилище-memory-vs-redis)
9. [Webhook-режим](#webhook-режим)
10. [Наблюдаемость](#наблюдаемость)
11. [Конфигурация](#конфигурация)
12. [Docker-развёртывание](#docker-развёртывание)
13. [Разработка](#разработка)
14. [Тестирование](#тестирование)
15. [Модель безопасности](#модель-безопасности)
16. [Структура репозитория](#структура-репозитория)
17. [Карта документации](#карта-документации)
18. [Траблшутинг](#траблшутинг)

---

## Что делает система

### Ценность для пользователя

1. **Загрузка** предложений кешбэка из любого банка тремя путями:
   - **Загрузка скриншота** → OCR-конвейер извлекает строки `Категория: N%`.
   - **`/quickadd Tinkoff: АЗС 5%, Рестораны 3%`** → банк настраивается
     одним сообщением.
   - **Шаблонный ручной ввод** → предзаполненные категории для популярных
     российских банков, правка процентов inline.
2. **Проверка и редактирование** — предпросмотр каждой черновой записи до
   сохранения, последующая правка.
3. **Ранжирование и поиск** — «Какая карта для `рестораны`?» /
   `/best рестораны` / inline-режим `@your_bot фастфуд` дают один и тот же
   ответ.
4. **Актуальность** — ежемесячные напоминания, чтобы пользователь обновлял
   данные до смены кешбэка.

### Production-готовность

- **Горизонтальное масштабирование** через webhook-режим и Redis для FSM
  (состояние бота переживает деплои, OOM-kill'ы, crash'ы).
- **Наблюдаемость**: structured JSON-логи с correlation id на запрос,
  Prometheus `/metrics`, глубокий `/health` (БД + Telegram + OCR).
- **Защищённость**: CORS, security-заголовки, rate-limit на API,
  bearer-токен для `/metrics`, отказ от старта при дефолтном
  `WEB_SESSION_SECRET`.
- **Кеширование**: нормализация категорий (LRU 2048), снимки ранжирования
  (30 с TTL на пользователя, invalidation при записи).
- **Без N+1**: чтение ранжирования — один JOIN `banks × cashback_items`.
- **Слоистая архитектура**: `domain → application → adapters`, проверяется
  boundary-тестами — случайно импортировать `aiogram` в `app/domain` не
  получится.

---

## Ключевые возможности

| Область | Что реализовано | Где |
|---|---|---|
| Мульти-адаптерное ядро | Telegram и Web через общий `handle_command(user, state, cmd) → Screen` | `app/application/facade.py` |
| OCR-конвейер | Tesseract локально, OpenAI Vision — только fallback на пустой/таймаут | `app/adapters/ocr_composite/` |
| Inline `@bot <query>` | Автокомплит из любого чата + deep-link обратно в бот | `app/adapters/telegram/inline.py` |
| Мульти-банк `/quickadd` | Параграфный ввод, rapidfuzz-подсказки на незнакомые категории | `app/application/use_cases/quick_add_bank.py` |
| Нормализация категорий | 28 slug'ов × RU/EN синонимы + fuzzy + LRU | `app/domain/services/categories.py` |
| Чтение ранжирования | 1 запрос JOIN + 30s TTL на пользователя | `app/adapters/postgres/repositories.py`, `app/application/use_cases/ranking_snapshot.py` |
| FSM-состояние | MemoryStorage или RedisStorage через `FSM_STORAGE` | `app/bootstrap/runtime.py::build_fsm_storage` |
| Webhook | POST /bot/webhook с `X-Telegram-Bot-Api-Secret-Token` | `app/adapters/web/app.py`, `runtime.py::_run_webhook_adapter` |
| Aiogram middleware | Logging (correlation id), throttling (30/min/user), user-context | `app/adapters/telegram/middleware.py` |
| Web middleware | CORS, security headers, rate-limit, correlation id, Prometheus | `app/adapters/web/app.py` |
| Structured logs | structlog + JSON в prod / Console в dev + correlation ids | `app/bootstrap/logger.py` |
| Health и metrics | GET /health (503 при degraded) + GET /metrics (bearer-токен) | `app/adapters/web/app.py` |
| Напоминания | Ежемесячные, через scheduler, только `notifications_enabled` | `app/adapters/scheduler/`, `app/application/use_cases/send_monthly_reminders.py` |
| Локализация | `ru.json` / `en.json`, Localizer с fallback | `app/i18n/localizer.py`, `app/locales/` |
| 372 теста | Unit + architecture + repository (sqlite in-memory) + web (httpx ASGI) | `tests/` |

---

## Быстрый старт

### 1) Требования

| Требование | Версия |
|---|---|
| Python | 3.11+ (рекомендуется 3.12) |
| PostgreSQL | 15+ (SQLite — только для тестов) |
| Tesseract OCR | 5.x, с языковым пакетом `rus` |
| Redis | 7.x (опционально — только при `FSM_STORAGE=redis`) |
| Docker | Опционально, есть compose |

### 2) Локальный запуск (без Docker)

```bash
# Виртуальное окружение
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Unix
source .venv/bin/activate

# Зависимости
pip install -r requirements.txt

# Настройка
cp .env.example .env
# Открой .env и минимум задай: BOT_TOKEN, POSTGRES_*, OPENAI_API_KEY (опц.)

# Запуск
python -m app.main
```

На старте runtime:

1. Загрузит `Settings` (Pydantic v2 из env/`.env`).
2. Настроит structlog.
3. Проверит существование БД PostgreSQL (создаст при `AUTO_CREATE_DB=true`).
4. Подождёт готовность БД с ретраями.
5. Применит Alembic-миграции (при `AUTO_MIGRATE=true`).
6. Соберёт DI-контейнер.
7. Запустит активные адаптеры (Telegram polling/webhook, web-сервер,
   reminder loop).

### 3) Docker

```bash
cp .env.example .env
# Заполни BOT_TOKEN, OPENAI_API_KEY (опц.), WEB_SESSION_SECRET

docker compose up --build -d

# Логи
docker compose logs -f bot

# Остановка
docker compose down
```

По умолчанию docker-compose запускает:

- `db` — PostgreSQL 16 на порту `5432`
- `redis` — Redis 7 на `6379` (нужен для `FSM_STORAGE=redis`)
- `bot` — Telegram-адаптер в polling-режиме
- `web` — FastAPI на `8080`

Сервисы `bot` и `web` используют один образ из `Dockerfile`; различаются
только `APP_ENABLE_TELEGRAM` / `APP_ENABLE_WEB`.

### 4) Проверка работоспособности

```bash
# Health check (работает при APP_ENABLE_WEB=true)
curl http://localhost:8080/health
# {"status":"ok","db":"ok","telegram":"ok","ocr":{...},"version":"<sha>"}

# Telegram — открой бот и отправь /start
```

---

## Архитектура на пальцах

### Слои ядра

```
┌────────────────────────────────────────────────────────────┐
│  Bootstrap  (runtime wiring, DI, миграции)                  │
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
│  Domain  (бизнес-правила: categories, ranking, parser)      │
└────────────────────────────────────────────────────────────┘
```

### Правила слоёв (проверяются `tests/test_architecture_boundaries.py`)

| Правило | Зачем |
|---|---|
| `app/domain` **не** может импортировать `aiogram`, `fastapi`, `sqlalchemy`, `app.adapters.*` | Домен — без транспорта и фреймворков |
| `app/application` **не** может импортировать `aiogram`, `fastapi`, `sqlalchemy`, `app.adapters.*` | Application работает только через порты |
| `app/adapters/web` **не** может импортировать `app.adapters.telegram.*` | Адаптеры — равные соседи, общие утилиты живут в `app/adapters/rate_limit.py` |
| `app/application/workflow` / `presenters` **не** упоминают `UnitOfWorkPort`, `uow_factory`, `AsyncSession` | Persistence — для use cases, не для workflow/presentation |

### Жизненный цикл запроса

```
Telegram update (polling или webhook)
  ↓
LoggingMiddleware ставит correlation_id + запускает таймер метрик
  ↓
UserContextMiddleware кладёт tg_user_id / tg_language_code в data
  ↓
ThrottlingMiddleware проверяет per-user-бакет (30/мин по умолчанию)
  ↓
Router превращает update → UserCommand
  ↓
ApplicationFacade.handle_command(user, state, cmd)
  ↓
Use case (normalize category / save draft / rank / …)
  ↓
UoW (SQLAlchemy async session) через BankRepositoryPort / …
  ↓
PostgreSQL (или SQLite в тестах)
  ↓
Возвращает Screen + Effects → Renderer → обратно пользователю
  ↓
LoggingMiddleware записывает latency/status → Prometheus + лог
```

Веб-запросы — та же схема, только `_CorrelationIdMiddleware` (X-Request-Id)
вместо Telegram-стека и `WebDependencies` вместо `TelegramDependencies`.

Подробные диаграммы и инварианты — в [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Команды Telegram и текстовые намерения

Бот публикует свои команды через `set_my_commands` при старте:

| Команда | Что делает |
|---|---|
| `/start` | Запуск бота. Поддерживает deep-link payload'ы: `?start=inline_setup` → «добавить банк»; `?start=add_bank` / `?start=top` / `?start=help` — аналогично. |
| `/best <категория>` | «Лучшая карта для X» — тот же путь, что и inline. Без аргумента — открывает полный рейтинг. |
| `/quickadd Tinkoff: АЗС 5%, Рестораны 3%` | Создать или заменить банк одним сообщением. Поддерживает **мультибанк**: блоки разделяются пустой строкой. |
| `/banks` | Список сохранённых банков. |
| `/top` | Полный рейтинг. Empty-state → CTA «Добавить первый банк». |
| `/settings` | Язык, уведомления. |
| `/help` | Список команд и текстовых намерений. |
| `/home` | Вернуться в главное меню. |
| `/cancel` | Отменить текущий черновик и вернуться домой. |

### Свободный текст

Сообщения без слэша проходят через маппер намерений:

| Ввёл пользователь | Маппится в |
|---|---|
| "домой" / "home" | `/home` |
| "помощь" / "help" | `/help` |
| "рестораны" (любая фраза-категория) | `/best рестораны` |
| "5% где" | Inline-поиск |

### Inline-режим

`@your_bot <запрос>` работает из любого чата — пользователь получает
автокомплит из своих лучших категорий. Нажатие результата — deep-link
обратно в бот с преднастроенной категорией. См. `app/adapters/telegram/inline.py`.

### Ограничения

| Поверхность | Лимит | Зачем |
|---|---|---|
| Фото (на пользователя) | Burst 5, refill 1 / 10 с | OCR дорогой — compute + возможно billed AI |
| Все сообщения / callback'и (на пользователя) | 30 / минуту (burst 30) | Глобальный лимит от абьюза через `ThrottlingMiddleware` |
| Inline-запросы | Без лимита | Read-only; критично для латентности автокомплита |
| Public `/api/*` (на IP) | `API_RATE_LIMIT_PER_MINUTE` (60 по умолч.) | Per-process bucket — для мульти-реплик используй edge-лимитер |

---

## Endpoint'ы веба

### Пользовательские (HTML SSR)

| Маршрут | Метод | Описание |
|---|---|---|
| `/` | GET | Лендинг — регистрация/логин + кнопка Telegram auth |
| `/app` | GET | Главная для авторизованного — та же Screen-модель, что и у бота |
| `/app/action` | POST | Action-команды (кнопки из UX) |
| `/app/input` | POST | Текстовый ввод |
| `/app/upload` | POST | Загрузка фото → OCR |
| `/auth/register`, `/auth/login`, `/auth/logout` | POST | Локальная авторизация |
| `/auth/telegram/callback` | GET | Верификация и привязка Telegram Login |
| `/auth/telegram/unlink` | POST | Отвязать Telegram identity |

### JSON API

| Маршрут | Метод | Auth | Описание |
|---|---|---|---|
| `/api/best?q=<category>` | GET | Session | Тот же ответ, что `/best` / inline-режим, в JSON — для скриптов и будущего мобильного клиента |

### Operations

| Маршрут | Метод | Auth | Описание |
|---|---|---|---|
| `/health` | GET | Нет | JSON-статус БД + Telegram + OCR + version. HTTP 503 при degraded. |
| `/metrics` | GET | Bearer (если задан `METRICS_TOKEN`) | Prometheus exposition format |
| `/bot/webhook` | POST | `X-Telegram-Bot-Api-Secret-Token` | Webhook-приёмник (активен при `WEBHOOK_ENABLED=true`) |

Заголовки ответа, выставляемые `_SecurityHeadersMiddleware`:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `X-Request-Id: <8-char uuid>` (возвращается для трейсинга)

---

## OCR-конвейер

Скриншоты банковских приложений — это преднамеренно тяжёлый кейс для OCR:
сжатый текст, смешанные RU/EN метки, цветные бейджи, тёмная тема. Настройка
`OCR_PROVIDER` выбирает движок:

| Провайдер | Поведение |
|---|---|
| `auto` (по умолч.) | **Локально-первый composite.** Tesseract идёт первым (бесплатно, локально); OpenAI Vision вызывается **только** если Tesseract вернул пусто или таймаут. При пустом `OPENAI_API_KEY` `auto` вырождается в чистый Tesseract. |
| `tesseract` | Только Tesseract — для полностью offline или жёстких budget-лимитов. |
| `openai` | Только OpenAI-совместимый vision (без локального fallback). Работает с любыми совместимыми endpoint'ами: реальный OpenAI, ProxyAPI, VSEgpt, self-hosted Ollama / LM Studio, Together, Groq. |

### Правила escalation для `auto`

| Ошибка | Эскалировать в vision? |
|---|---|
| `errors.ocr_empty` | ✅ — Tesseract не распознал, AI может |
| `errors.ocr_timeout` | ✅ — Tesseract завис, пробуем AI |
| `errors.broken_image` | ❌ — битые байты, оба движка упадут |
| `errors.file_too_large` | ❌ — нечего платить за round-trip |

### Защита от кривого ответа модели

OpenAI-адаптер закалён всеми ситуациями из прода:

- **Markdown-обёртка** (```json ... ```) — срезается
- **Болтовня модели** («Вот JSON:\n\n{…}») — JSON извлекается
- **Проценты > 100 или < 0** — обрезаются/отбрасываются, `errors.ocr_parse_invalid`
- **Дубли категорий** — дедуп с выбором максимального процента
- **Rate-limit / auth ошибки** — мапятся в `errors.ocr_unavailable`
- **Кривой JSON** — → `errors.ocr_parse_invalid`
- **Нет `content_type`** — по умолчанию `image/jpeg`

Всё мапится в существующие `errors.*` ключи перевода — UX не меняется от
того, какой движок ответил.

### Typing-indicator

Во время OCR бот посылает `chat_action=typing` с 4-секундным refresh-циклом
(`_with_typing` в `app/adapters/telegram/router.py`), чтобы пользователь не
видел 2–10 секунд тишины, пока Tesseract + AI работают. Refresher-таск
снимается сразу, как только OCR-корутина завершается или бросает — утечек
фоновых тасок нет.

---

## FSM-хранилище: Memory vs Redis

FSM хранит состояние wizard'а на пользователя: на каком шаге «добавить
банк» он находится, текущий черновик, ожидаемый ввод.

| Режим | Когда использовать | Минус |
|---|---|---|
| `FSM_STORAGE=memory` (по умолчанию) | Локалка, тесты, одноразовые single-process сетапы | **Теряется на перезапуске** — пользователи в середине wizard'а возвращаются на home |
| `FSM_STORAGE=redis` | Production | Нужен доступный Redis (`REDIS_URL`) |

Ключи Redis префиксуются `cashback_fsm:`, чтобы можно было делить instance с
другими приложениями. Если `FSM_STORAGE=redis` при пустом `REDIS_URL`,
runtime пишет warning и откатывается в память — старт не падает.

**Рекомендация:** Redis в prod, memory во всём остальном.

```env
FSM_STORAGE=redis
REDIS_URL=redis://redis:6379/0
```

---

## Webhook-режим

Polling нормален для dev и небольших деплоев, но не масштабируется
горизонтально — каждая реплика бота тянула бы независимо, а Telegram не
балансирует. В production — webhook: Telegram POST'ит апдейты на ваш HTTPS
endpoint, FastAPI-приложение прогоняет их через тот же aiogram Dispatcher.

### Требования

- **Публичный HTTPS-endpoint**, резолвящийся серверами Telegram.
- **`APP_ENABLE_WEB=true`** — обработчик webhook живёт в FastAPI-приложении.
- **`APP_ENABLE_TELEGRAM=true`** — всё равно нужен bot-токен и dispatcher.
- **`WEBHOOK_ENABLED=true`**.
- **`WEBHOOK_SECRET`** — случайная строка (~32 символа). Telegram отдаст её
  в заголовке `X-Telegram-Bot-Api-Secret-Token`; handler отвечает 403 при
  несовпадении.

### Настройка

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=true
WEBHOOK_PATH=/bot/webhook
WEBHOOK_SECRET=<openssl rand -hex 32>
WEB_BASE_URL=https://your-domain.com
WEB_SESSION_SECRET=<ещё один сильный секрет>
```

На старте runtime вызывает `bot.set_webhook(url=f"{WEB_BASE_URL}{WEBHOOK_PATH}",
secret_token=WEBHOOK_SECRET, drop_pending_updates=True)`. На shutdown —
`bot.delete_webhook()`, чтобы следующее polling-развёртывание не
конфликтовало со старым webhook'ом.

### Возврат к polling

Поставь `WEBHOOK_ENABLED=false` (или не выставляй `APP_ENABLE_WEB`).
Polling-режим перед стартом сам вызывает `bot.delete_webhook()` — можно
переключать без ручной очистки.

---

## Наблюдаемость

### Структурированные логи

`configure_logging(level)` обвязывает stdlib logging через structlog:

- Development (`LOG_LEVEL=DEBUG`): цветной `ConsoleRenderer`.
- Production (любой другой уровень): `JSONRenderer` → одна JSON-строка на
  событие, готово к Loki / Elasticsearch / CloudWatch / Datadog.

Каждая запись несёт **correlation_id**:

- Telegram: выставляется `LoggingMiddleware` на update (uuid4-префикс, 8 символов).
- Web: выставляется `_CorrelationIdMiddleware` на запрос (читает заголовок
  `X-Request-Id` или генерирует; возвращает в ответе).

Одно действие пользователя можно грепать по одному id во всех слоях —
адаптер, application, repository.

### Prometheus-метрики

Выставлены на `/metrics`:

| Метрика | Тип | Лейблы | Источник |
|---|---|---|---|
| `cashback_bot_requests_total` | Counter | `handler`, `status` | `LoggingMiddleware` |
| `cashback_bot_request_duration_seconds` | Histogram | `handler` | `LoggingMiddleware` |
| `cashback_bot_ocr_calls_total` | Counter | `provider`, `result` | OCR-адаптеры (будущая обвязка) |
| `cashback_bot_active_users_total` | Gauge | — | `LoggingMiddleware.observe_user` |

Защищены bearer-токеном при `METRICS_TOKEN`:

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8080/metrics
```

### Health check

`GET /health` возвращает:

```json
{
  "status": "ok",
  "db": "ok",
  "telegram": "ok",
  "ocr": {"primary": "auto", "status": "ok"},
  "version": "<git-sha>"
}
```

- `db`-проба: `SELECT 1` с таймаутом 2 с.
- `telegram`-проба: `bot.get_me()` с таймаутом 3 с (скипается, если
  `APP_ENABLE_TELEGRAM=false`).
- `n/a`: проба не подключена в этом режиме — **не** триггерит degraded.

HTTP-статусы: `200 ok`, `503 degraded`. Можно использовать как Kubernetes
`readinessProbe` / `livenessProbe`.

Docker-образ содержит `HEALTHCHECK`:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1
```

---

## Конфигурация

Все настройки — через `app/bootstrap/config.py::Settings` (Pydantic v2).
Каждое поле имеет `Field(..., alias="ENV_NAME")`, так что переопределяется
через env или `.env`.

### Обязательные

| Env | Default | Когда |
|---|---|---|
| `BOT_TOKEN` | `123456:TEST_TOKEN` | Нужен при `APP_ENABLE_TELEGRAM=true` или включённом web Telegram-login |
| `TELEGRAM_BOT_USERNAME` | `""` | Нужен при `APP_ENABLE_WEB=true` (для Telegram Login widget) |
| `POSTGRES_*` или `DATABASE_URL` | `postgresql+asyncpg://cashback_user:cashback_password@localhost:5432/cashback_bot` | Любой деплой на Postgres |

### Режимы запуска

| Env | Значения | Default |
|---|---|---|
| `APP_ENABLE_TELEGRAM` | `true` / `false` | `true` |
| `APP_ENABLE_WEB` | `true` / `false` | `false` |
| `WEB_ENABLE_TELEGRAM_AUTH` | `true` / `false` | `true` |

### OCR

| Env | Default | Комментарий |
|---|---|---|
| `OCR_PROVIDER` | `auto` | `auto` / `tesseract` / `openai` |
| `OPENAI_API_KEY` | `""` | Нужен для `openai`, используется в `auto` fallback |
| `OPENAI_BASE_URL` | `""` | Override для OpenAI-совместимых шлюзов |
| `OPENAI_MODEL` | `gpt-4o` | Любая vision-совместимая модель |
| `OPENAI_VISION_TIMEOUT` | `60` | Секунды |
| `OPENAI_VISION_MAX_TOKENS` | `1024` | Safety-bound |
| `OCR_TIMEOUT` | `20` | Tesseract timeout в секундах |
| `MAX_FILE_SIZE` | `5242880` | 5 МиБ upload cap |
| `TESSERACT_PATH` | `tesseract` | Абсолютный путь, если бинарь не в `$PATH` |

### FSM и Webhook

| Env | Default | Комментарий |
|---|---|---|
| `FSM_STORAGE` | `memory` | `memory` / `redis` |
| `REDIS_URL` | `""` | Напр. `redis://redis:6379/0` |
| `WEBHOOK_ENABLED` | `false` | Требует `APP_ENABLE_WEB=true` |
| `WEBHOOK_PATH` | `/bot/webhook` | Только path-часть |
| `WEBHOOK_SECRET` | `""` | Рекомендуется — включает проверку заголовка |

### Web

| Env | Default | Комментарий |
|---|---|---|
| `WEB_HOST` | `0.0.0.0` | |
| `WEB_PORT` | `8080` | |
| `WEB_BASE_URL` | `http://localhost:8080` | Используется для Telegram Login redirect и webhook URL |
| `WEB_SESSION_SECRET` | `change-me-session-secret` | **Обязательно сменить** при `APP_ENABLE_WEB=true` — иначе Settings откажется конструироваться |
| `WEB_SECURE_COOKIES` | `false` | `true` за HTTPS |
| `WEB_MAX_UPLOAD_SIZE` | `5242880` | Верхняя граница body на `/app/upload` |

### Безопасность

| Env | Default | Комментарий |
|---|---|---|
| `CORS_ORIGINS` | `*` | Список через запятую; wildcard только для dev |
| `METRICS_TOKEN` | `""` | Пусто → `/metrics` открыт (dev-удобство). В prod — задать. |
| `API_RATE_LIMIT_PER_MINUTE` | `60` | Per-IP token bucket на `/api/*` |

### БД / миграции

| Env | Default | Комментарий |
|---|---|---|
| `AUTO_CREATE_DB` | `true` | Создаёт БД, если её нет |
| `AUTO_MIGRATE` | `true` | Запускает `alembic upgrade head` при старте |
| `DB_POOL_SIZE` | `10` | SQLAlchemy async pool size |
| `DB_MAX_OVERFLOW` | `20` | Overflow-соединения |
| `DB_POOL_TIMEOUT` | `30` | Секунды ожидания свободного соединения |
| `DB_POOL_RECYCLE` | `300` | Секунды до recycle соединения |
| `DB_CONNECT_MAX_ATTEMPTS` | `20` | Budget на readiness-ретраи |
| `DB_CONNECT_RETRY_DELAY` | `2.0` | Секунды между ретраями |
| `MIGRATION_MAX_ATTEMPTS` | `10` | Budget для Alembic |
| `MIGRATION_RETRY_DELAY` | `2.0` | Секунды между ретраями миграций |

### Прочее

| Env | Default | Комментарий |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` → console renderer |
| `LANG_DEFAULT` | `ru` | `ru` / `en` |
| `APP_TIMEZONE` | `Europe/Moscow` | Для расписания напоминаний |
| `REMINDER_HOUR` | `10` | Местный час, когда шлётся ежемесячное |
| `TELEGRAM_RETRY_DELAY` | `5.0` | Polling backoff на transient errors |
| `TEMP_DIR` | `ocr_tmp` | OCR temp-файлы (создаётся автоматически) |

Полный справочник: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

---

## Docker-развёртывание

### docker-compose.yml

```yaml
services:
  db:      postgres:16-alpine, порт 5432, healthcheck pg_isready
  redis:   redis:7-alpine, порт 6379, healthcheck redis-cli ping
  bot:     python-образ (этот репо), APP_ENABLE_TELEGRAM=true
  web:     python-образ, APP_ENABLE_WEB=true, порт 8080
```

Оба сервиса `bot` и `web`:

- Зависят от healthy `db` и `redis`.
- Наследуют один образ из `Dockerfile` (python:3.11-slim + tesseract).
- Запускают `python -m app.main` — флаги `APP_ENABLE_*` определяют, что
  стартует.
- Работают под non-root пользователем `cashback` (UID 10001).
- Имеют `HEALTHCHECK CMD curl -fsS http://127.0.0.1:8080/health || exit 1`.

### Production-чеклист

- [ ] `BOT_TOKEN` задан (реальный, не placeholder)
- [ ] `TELEGRAM_BOT_USERNAME` задан
- [ ] `WEB_SESSION_SECRET` сгенерирован (`openssl rand -hex 32`)
- [ ] `WEB_SECURE_COOKIES=true` (за HTTPS)
- [ ] `FSM_STORAGE=redis` + `REDIS_URL` указывает на Redis
- [ ] `WEBHOOK_ENABLED=true` + `WEBHOOK_SECRET` заданы (если webhook)
- [ ] `METRICS_TOKEN` задан
- [ ] `CORS_ORIGINS` сужен до реальных origin'ов фронта
- [ ] Postgres backup'ится по расписанию
- [ ] HTTPS reverse-proxy (nginx, Caddy, Traefik) перед web
- [ ] Мониторинг: scrape `/metrics`, алерт на не-200 `/health`

Оперативный runbook: [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

---

## Разработка

### Запуск тестов

```bash
# Полный прогон (372 теста, ~1–2 минуты на Windows)
python -m pytest -q

# Один файл
python -m pytest tests/test_middleware.py -q

# Один тест
python -m pytest tests/test_middleware.py::test_throttling_middleware_allows_up_to_capacity -q

# С выводом
python -m pytest -v
```

### Добавить новый use case

1. **Объявить port** (если нужна новая persistence/transport-граница) в
   `app/application/contracts/ports.py`.
2. **Добавить use case** в `app/application/use_cases/` — один файл, один класс.
3. **Написать тест первым** в `tests/`. Используй `uow_factory` из
   `conftest.py` — in-memory UoW для быстрых unit-тестов.
4. **Реализовать конкретный адаптер** в `app/adapters/postgres/` (если
   новая persistence-поверхность).
5. **Прокинуть в контейнер** `app/bootstrap/container.py`.
6. **Выставить через facade** `app/application/facade.py`, если адаптеры
   его зовут.
7. **Вызвать из workflow / router** в `app/application/use_cases/handle_command.py`
   или маршруте адаптера.

### Добавить локализационную строку

1. Добавь `your.new.key` в **оба** `app/locales/ru.json` и
   `app/locales/en.json`. Несовпадения работают runtime (fallback в default),
   но держи в синхроне, чтобы не огребать сюрпризов в prod.
2. Используй как `localizer.t("your.new.key", language)`.
3. Для ключей-ошибок ставь префикс `errors.*` — router-recovery
   (`_OCR_RETRYABLE_KEYS`) смотрит именно на него.

### Запустить только бот или только web

```bash
APP_ENABLE_TELEGRAM=true APP_ENABLE_WEB=false python -m app.main
APP_ENABLE_TELEGRAM=false APP_ENABLE_WEB=true python -m app.main
```

### Alembic

```bash
# Сгенерировать миграцию из изменений моделей
alembic revision --autogenerate -m "add_new_index"

# Применить миграции
alembic upgrade head

# Откатить на один шаг
alembic downgrade -1
```

Гайд по разработке: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

---

## Тестирование

### Слои тестов

| Слой | Скорость | Зависимости | Количество (прим.) |
|---|---|---|---|
| Domain unit | <10 мс | Pure Python | ~60 |
| Application unit | <50 мс | In-memory UoW из `conftest.py::InMemoryUnitOfWork` | ~120 |
| Adapter (postgres) | ~300 мс | `sqlite+aiosqlite` через `StaticPool` | ~15 |
| Web | ~500 мс | `httpx.AsyncClient` + `ASGITransport` | ~40 |
| Telegram router | ~200 мс | `MagicMock` bot, реальный router | ~20 |
| Architecture boundary | <50 мс | AST-walk | ~5 |
| Scenario regressions | ~500 мс | Полный facade + in-memory UoW | ~20 |

### Важные фикстуры (`tests/conftest.py`)

- `store` — bare `InMemoryStore` dataclass.
- `uow_factory` — возвращает zero-arg callable, создающий новую
  `InMemoryUnitOfWork` на общем `store`.
- `dummy_ocr` — OCR-port stub, настраивается `dummy_ocr.value = "АЗС 5%"`.

### Smoke «золотого пути»

```bash
python -m pytest -q tests/test_scenario_regressions.py
```

Scenario-regression тесты проигрывают реальные user flow (добавь банк →
правь проценты → удали item → спроси best card) поверх in-memory
container — ловят регрессии, которые пропустил бы узкий unit-тест.

### Что должен крутить CI

```bash
python -m pytest -q                    # все тесты
python -m compileall app tests         # синтаксис
docker compose config -q               # compose-синтаксис
```

---

## Модель безопасности

### Идентификация

- Web-пользователи могут существовать **без** Telegram (локальные
  креденшиалы).
- Telegram-идентификации привязываются к существующему аккаунту из
  авторизованной сессии.
- Непривязанный Telegram-callback не создаёт silent web-сессию.
- `user_identities` хранит `(provider, provider_user_id)` как уникальный
  ключ.

### Пароли

- Argon2 (`argon2-cffi`), дефолтные параметры.
- Нормализация на входе: email в lowercase, trim username.
- Никогда не логируются, не сериализуются в тело ответа.

### Сессии

- `SessionMiddleware` (starlette), подписано `WEB_SESSION_SECRET`.
- `max_age=14 дней`, `same_site=lax`.
- `https_only=WEB_SECURE_COOKIES` (ставь `true` в prod).
- Settings отказывается конструироваться при `APP_ENABLE_WEB=true` и
  дефолтном session secret.

### CSRF

- Сессионные cookie — `same_site=lax`, большинство cross-site атак не
  проходит.
- `/api/best` — только GET, требует авторизованной сессии.
- Form posts на `/app/action`, `/app/input`, `/app/upload` — с session-gate.

### Rate-лимиты

См. таблицу в разделе [Команды Telegram](#команды-telegram-и-текстовые-намерения).

### Метрики

- `/metrics` показывает внутренние имена. Защищайте `METRICS_TOKEN` в
  любом деплое, доступном из интернета.

### Зависимости

- `pip-audit` в CI пока нет — в roadmap. Пока `requirements.txt` пинит
  major + minor floor'ы до трекаемых диапазонов.

---

## Структура репозитория

```
cashback_bot/
├── alembic/                   # Миграции БД
│   └── versions/
│       ├── 20260306_0001_initial.py
│       ├── 20260311_0002_platform_identity.py
│       └── 20260424_0003_performance_indexes.py
├── app/
│   ├── main.py                # Точка входа — python -m app.main
│   ├── domain/                # Чистые бизнес-правила
│   ├── application/           # Use cases, ports, facade
│   ├── adapters/              # postgres / telegram / web / ocr_* / …
│   ├── bootstrap/             # config, container, runtime, logger
│   ├── i18n/localizer.py
│   └── locales/               # ru.json, en.json
├── docs/                      # Архитектура, dev, ops, конфиг
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   ├── OPERATIONS.md
│   ├── CONFIGURATION.md
│   ├── PRODUCT_OVERVIEW.md
│   ├── USER_FLOWS.md
│   ├── WEB_USER_CASES.md
│   └── ru/                    # Русские переводы
├── tests/                     # 372 теста
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
├── pytest.ini
├── README.md                  # Английская версия
└── README.ru.md               # Этот файл
```

---

## Карта документации

| Документ | Назначение |
|---|---|
| [README.md](README.md) | Английский README |
| [README.ru.md](README.ru.md) | Этот файл |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Слои, порты, инварианты, runtime flow |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Dev setup, обычные задачи, режимы |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Deploy, webhook, мониторинг, runbook |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Полный справочник env-переменных |
| [docs/PRODUCT_OVERVIEW.md](docs/PRODUCT_OVERVIEW.md) | Бизнес-домен, roadmap |
| [docs/USER_FLOWS.md](docs/USER_FLOWS.md) | Пользовательские сценарии пошагово |
| [docs/WEB_USER_CASES.md](docs/WEB_USER_CASES.md) | Web-специфичные use case'ы |
| [docs/architecture/](docs/architecture/) | Архитектурные deep-dive'ы |
| [docs/audits/](docs/audits/) | Прошлые аудиты / находки |
| [docs/migrations/](docs/migrations/) | Runbook'и миграций |

---

## Траблшутинг

### «Бот не отвечает»

1. Проверь `/health` → `telegram: ok`? Если `error`, `bot.get_me()` падает —
   почти всегда это невалидный `BOT_TOKEN`.
2. В webhook-режиме — дёрни `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`.
   `last_error_date` покажет проблему (обычно TLS, DNS или 5xx).
3. В polling-режиме — ищи в логах `TelegramUnauthorizedError` (плохой токен)
   или частые `TelegramNetworkError` (firewall / DNS).

### «OCR ничего толкового не возвращает»

1. Убедись, что `OCR_PROVIDER=auto` и `OPENAI_API_KEY` задан — один
   Tesseract плохо справляется с dark-тема банк-скринами.
2. Проверь `/metrics` → `cashback_bot_ocr_calls_total{result="error"}` растёт?
3. Лог-строка `errors.ocr_empty` несёт сырой вывод Tesseract'а — грепай,
   чтобы увидеть, что он всё-таки прочитал.

### «Пользователи теряют wizard-состояние после деплоя»

Ты на `FSM_STORAGE=memory`. Переключи на redis:

```env
FSM_STORAGE=redis
REDIS_URL=redis://redis:6379/0
```

### «/metrics отдаёт 401»

`METRICS_TOKEN` задан. Либо:

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8080/metrics
```

Либо убери `METRICS_TOKEN` (НЕ для prod).

### «Settings() на старте бросает ValueError»

`APP_ENABLE_WEB=true` при всё ещё дефолтном
`WEB_SESSION_SECRET=change-me-session-secret`. Сгенерируй:

```bash
openssl rand -hex 32
# → скопируй в WEB_SESSION_SECRET
```

### «Rate-limit срабатывает на моих же тестах»

`API_RATE_LIMIT_PER_MINUTE=60` на `/api/*` на IP. Для нагрузочных:

```env
API_RATE_LIMIT_PER_MINUTE=10000
```

### «Webhook Telegram отвечает 403»

Заголовок `X-Telegram-Bot-Api-Secret-Token` в запросе не совпадает с
`WEBHOOK_SECRET`. Перезвоните `bot.set_webhook(secret_token=...)` с новым
значением или приведи env-переменную к тому, что Telegram сейчас шлёт.

---

## Лицензия и вклад

Репозиторий приватный. Политика вкладов на усмотрение владельца. Для
внешних предложений — откройте issue с описанием.

По вопросам и feedback — GitHub issue либо прямой контакт с владельцем
репозитория.

---

*Сгенерировано в рамках production-hardening цикла `cashback_analyzer`.*
*Все описанные примеры и поведения покрыты тестами в `tests/` и
верифицируются локально через `python -m pytest -q`.*
