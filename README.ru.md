# Cashback Analyzer

Cashback Analyzer — это core-first платформа для анализа банковских cashback-категорий с двумя внешними адаптерами:

- Telegram-бот на `aiogram 3`
- веб-приложение на `FastAPI` + SSR mobile-first UI

Продукт хранит и сравнивает актуальные cashback-предложения по банкам и картам пользователя. Он не ведёт учёт транзакций, начисленного cashback, расходов или бюджета.

## Карта документации

- [Англоязычный README](README.md)
- [Обзор продукта](docs/ru/PRODUCT_OVERVIEW.md)
- [Архитектура](docs/ru/ARCHITECTURE.md)
- [Разработка и запуск](docs/ru/DEVELOPMENT.md)
- [Пользовательские сценарии](docs/ru/USER_FLOWS.md)
- [Web user cases](docs/ru/WEB_USER_CASES.md)
- [Repository Integrity Audit (historical snapshot)](docs/audits/repository-integrity-audit.md)

## Краткое описание

Проект — это кроссплатформенное приложение для управления банковским cashback. Оно помогает пользователю собрать данные по картам из разных банков, проверить и отредактировать их, а затем получить практическую рекомендацию, какой картой выгоднее платить в конкретной категории.

## Бизнес-цель

Система нужна для того, чтобы пользователь быстро понимал, какой картой выгоднее платить в реальной жизненной ситуации.

Это не бухгалтерский продукт. Это decision-support продукт для оптимизации cashback:

- собрать предложения разных банков
- привести их к сопоставимой модели
- дать пользователю проверить и исправить данные
- выдать практическую рекомендацию по категории или сценарию покупки

## Что система умеет

- Аутентифицирует Telegram identity через общий external-identity flow.
- Поддерживает локальную web-регистрацию и вход.
- Собирает cashback-категории со скриншотов через OCR.
- Принимает скриншоты прямо с web home screen и направляет распознанные категории в attach-to-bank flow.
- Поддерживает ручной ввод и template-based draft creation.
- Нормализует категории по RU/EN синонимам.
- Даёт редактировать draft и уже сохранённые банковские данные.
- Хранит cashback-категории как month-aware snapshots для previous/current/next month.
- Строит лидеров по категориям, глобальный рейтинг банков и best-bank ответы.
- Хранит историю действий в `user_logs`.
- Отправляет ежемесячные reminders пользователям с включёнными уведомлениями.
- Запускает планировщик reminders на уровне application runtime, а не внутри Telegram polling lifecycle.
- Запускает Telegram и web adapters независимо через feature flags.

## Текущий baseline и product vision

Текущий baseline уже поддерживает:

- OCR/manual/template ingestion
- прямую загрузку скриншота с web home screen
- automatic attach-to-bank flow после OCR/manual parsing
- month-aware cashback snapshots
- draft preview и editing
- редактирование сохранённых банков
- category ranking и best-match lookup
- settings, reminders, history
- local web auth и Telegram identity linking
- web и Telegram adapters поверх одного application core

Следующий продуктовый слой может дополнительно включать:

- card-level metadata
- cashback limits и validity windows
- более сложную decision logic
- richer desktop analytics и bulk editing

## Кратко об архитектуре

Проект построен как core-first система:

- `app/domain`: чистые доменные модели, ошибки, enums, normalization, parsing, ranking
- `app/application`: auth use cases, business use cases, workflow contracts, workflow handlers, presenters, facade
- `app/adapters`: PostgreSQL, OCR, auth adapters, Telegram, web, scheduler, system
- `app/bootstrap`: configuration, dependency wiring, startup checks, migrations, runtime

Transport-neutral workflow entrypoint:

```python
handle_command(user, workflow_state, user_command) -> WorkflowResult
```

Текущая структура workflow:

- `app/application/workflow`: dispatcher, interrupt policy, draft flow, bank flow, navigation, text intents
- `app/application/presenters`: `Screen` builders и formatting helpers

Подробное описание — в [docs/ru/ARCHITECTURE.md](docs/ru/ARCHITECTURE.md).

## Структура репозитория

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

## Быстрый старт

### Локально

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

Чтобы добавить Telegram adapter и owner reminder delivery, запустите:

```bash
docker compose --profile telegram up --build
```

При старте приложение умеет:

- создавать PostgreSQL-базу, если `AUTO_CREATE_DB=true`
- применять Alembic migrations, если `AUTO_MIGRATE=true`
- по умолчанию запускать web adapter, а Telegram adapter поднимать только при включении compose profile `telegram`

## Основные переменные окружения

Полный список есть в [.env.example](.env.example). Ключевые переменные:

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

Важная оговорка:

- code defaults и `.env.example` теперь согласованы вокруг web-first local posture:
  - `APP_ENABLE_TELEGRAM=false`
  - `APP_ENABLE_WEB=true`
  - `WEB_ENABLE_TELEGRAM_AUTH=false`
  - `REMINDER_DELIVERY_PROVIDER=`
- `BOT_TOKEN` нужен только когда включён Telegram adapter, web Telegram auth или Telegram reminder delivery
- `TELEGRAM_BOT_USERNAME` нужен только для web Telegram auth

## Режимы запуска

- локальный web-first по умолчанию: `APP_ENABLE_TELEGRAM=false`, `APP_ENABLE_WEB=true`, `WEB_ENABLE_TELEGRAM_AUTH=false`, `REMINDER_DELIVERY_PROVIDER=`
- web с Telegram login/link: `APP_ENABLE_TELEGRAM=false`, `APP_ENABLE_WEB=true`, `WEB_ENABLE_TELEGRAM_AUTH=true`, `REMINDER_DELIVERY_PROVIDER=`
- только Telegram: `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=false`, `REMINDER_DELIVERY_PROVIDER=telegram`
- single-process hybrid: `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=true`, `WEB_ENABLE_TELEGRAM_AUTH=true`, `REMINDER_DELIVERY_PROVIDER=telegram`

Один и тот же application core обслуживает все режимы.

## Краткий user journey

1. Пользователь входит в продукт.
2. Сразу отправляет скриншот или выбирает manual/template input.
3. Подтверждает распознанные категории и привязывает их к банку.
4. Выбирает previous/current/next month.
5. Сохраняет активный snapshot предложения.
6. Позже спрашивает, какая карта лучше для категории.
7. Использует ranking output вместо ручного сравнения нескольких банковских приложений.

Подробная карта flow — в [docs/ru/USER_FLOWS.md](docs/ru/USER_FLOWS.md).

## Проверки

Полезные команды:

```bash
pytest -q
python -m compileall app tests
docker compose config -q
```

## Текущее состояние

Текущее архитектурное состояние:

- platform identity model активен
- local web auth активен
- Telegram — secondary external identity и delivery adapter
- workflow decomposition завершён для текущей фазы
- presentation helpers вынесены из workflow orchestration
- reminder scheduler принадлежит runtime, а не Telegram polling path

Residual technical debt перечислен в [docs/audits/repository-integrity-audit.md](docs/audits/repository-integrity-audit.md) как исторический аудит, а не как источник истины.
