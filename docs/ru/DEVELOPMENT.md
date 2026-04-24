# Разработка и запуск

## Требования

- Python 3.11+
- PostgreSQL 15+
- Tesseract OCR с русским языковым пакетом
- Docker Desktop для compose-based startup

## Локальная настройка

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

Запуском управляет `app/bootstrap/runtime.py`.

Runtime sequence:

1. загрузка settings
2. настройка logging
3. ожидание readiness базы
4. запуск Alembic migrations, если включены
5. сборка DI container
6. запуск runtime-owned reminder scheduling, если reminder delivery provider сконфигурирован
7. старт enabled adapters

## Основные переменные окружения

Источник settings: `app/bootstrap/config.py`

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

Операционная оговорка:

- code defaults и `.env.example` теперь согласованы вокруг web-first local mode
- `BOT_TOKEN` обязателен, когда включён Telegram bot adapter, web Telegram linking/login или `REMINDER_DELIVERY_PROVIDER=telegram`
- `TELEGRAM_BOT_USERNAME` нужен только для web Telegram linking/login
- `WEB_SESSION_SECRET` по умолчанию содержит development-only значение и должен быть переопределён в hardened environments

## Рекомендуемые режимы

### Local web-first по умолчанию

```env
APP_ENABLE_WEB=true
APP_ENABLE_TELEGRAM=false
WEB_ENABLE_TELEGRAM_AUTH=false
REMINDER_DELIVERY_PROVIDER=
```

### Web с Telegram login/link

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

## Reminder delivery runtime

- monthly reminder scheduling стартует из `app/bootstrap/runtime.py`
- scheduler больше не вложен в Telegram polling startup
- ownership reminder delivery теперь задаётся через `REMINDER_DELIVERY_PROVIDER`
- поддерживаемые значения сейчас: пусто/disabled и `telegram`
- в multi-service compose только один процесс должен владеть reminder delivery; bundled compose закрепляет это за Telegram profile service

## Auth Behavior

### Web

- local register: `POST /auth/register`
- local login: `POST /auth/login`
- logout: `POST /auth/logout`
- Telegram callback/link flow: `GET /auth/telegram/callback`
- Telegram unlink: `POST /auth/telegram/unlink`

### Telegram

Бот аутентифицирует пользователя через shared external identity use case и всё ещё может создать user при первом контакте.

## Архитектура workflow

Текущий workflow split:

- `app/application/workflow/dispatcher.py`
- `app/application/workflow/draft.py`
- `app/application/workflow/banks.py`
- `app/application/workflow/navigation.py`
- `app/application/workflow/text_intents.py`
- `app/application/workflow/interrupts.py`
- `app/application/presenters/workflow_screens.py`
- `app/application/presenters/workflow_formatters.py`

`app/application/use_cases/handle_command.py` остаётся только тонкой orchestration-обёрткой над dispatcher.

Текущее user-facing behavior, которое важно сохранять в tests:

- web home screen принимает screenshot upload сразу
- Telegram принимает фото и вне старого dedicated photo state
- OCR/manual parsing ведёт пользователя в attach-to-bank flow, а не останавливается после recognition
- если у пользователя ровно один сохранённый банк, категории auto-attach к нему
- preview и saved-bank flows month-aware (`previous`, `current`, `next`)

## Database Migration

Identity refactor вводит:

- nullable `users.telegram_user_id`
- `users.display_name`
- `user_identities`
- `local_credentials`
- `cashback_items.target_month`

Current compatibility posture после refactor:

- legacy `users.telegram_user_id`, `username` и `full_name` остаются в schema только как deprecated compatibility fields
- новые runtime writes больше не зеркалят linked Telegram identities обратно в эти колонки

Ручной запуск:

```bash
alembic upgrade head
```

Подробности — в `docs/migrations/identity-clean-break.md`.

## Docker

Старт стека:

```bash
docker compose up --build
```

Чтобы добавить Telegram runtime:

```bash
docker compose --profile telegram up --build
```

Design intent:

- оба adapters используют одну schema и один application core
- bot и web можно деплоить независимо
- migrations выполняются на старте, если включены

## Тестирование

Основные команды:

```bash
pytest -q
python -m compileall app tests
docker compose config -q
```

Текущее regression coverage включает:

- auth normalization и login flows
- external identity linking/unlinking
- repository behavior
- OCR adapter boundaries
- reminder routing через injected delivery providers over linked identities
- runtime ownership reminder loop вне Telegram adapter startup
- Telegram rendering и routing
- web adapter behavior
- month-aware repository behavior
- attach-after-OCR flow
- workflow interruption и recovery
- workflow decomposition boundaries

## Типовые dev-задачи

### Добавить новый business use case

1. определить или расширить application port при необходимости
2. добавить focused use case в `app/application/use_cases`
3. сначала покрыть его тестами
4. подключить его в `app/bootstrap/container.py`
5. вызывать его из workflow layer или adapter

### Добавить новый transport adapter

1. переиспользовать `ApplicationFacade`
2. маппить inbound events в `UserCommand`
3. хранить transport-specific session state вне core
4. рендерить `Screen` и `Action` в adapter-specific UX

### Расширить identity providers

1. добавить provider constant и adapter verification logic
2. сохранять provider + subject в `user_identities`
3. маршрутизировать auth через `AuthenticateExternalIdentityUseCase`
4. добавить adapter и integration tests

## Обработка ошибок

- не проглатывать exceptions молча
- логировать operational failures с контекстом
- возвращать короткие локализованные user-facing сообщения
- после recoverable failures сохранять valid workflow state

## Замечания по деплою

- установить сильный `WEB_SESSION_SECRET`
- включить HTTPS и secure cookies в production
- держать `WEB_ENABLE_TELEGRAM_AUTH=false`, если Telegram linking не нужен
- проверить `AUTO_MIGRATE` относительно deployment policy
- мониторить reminder delivery после identity migration
