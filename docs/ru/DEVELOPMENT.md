# Разработка и запуск

## Требования

- Python 3.11+
- PostgreSQL 15+
- Tesseract OCR с русским языковым пакетом
- Docker Desktop для контейнерного запуска

## Локальная настройка

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

`app.main` делегирует запуск в [app/bootstrap/runtime.py](C:\Users\Kuznetz\Desktop\proga\cashback_bot\app\bootstrap\runtime.py), который выполняет:

1. загрузку settings
2. настройку logging
3. опциональное создание базы
4. ожидание доступности подключения
5. запуск Alembic migrations
6. старт адаптеров

## Стратегия конфигурации

Источник settings: [app/bootstrap/config.py](C:\Users\Kuznetz\Desktop\proga\cashback_bot\app\bootstrap\config.py)

Группы переменных окружения:

- Telegram: `BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`
- Postgres: `POSTGRES_*`, опционально `DATABASE_URL`
- OCR: `TESSERACT_PATH`, `OCR_TIMEOUT`, `MAX_FILE_SIZE`
- Runtime: `APP_TIMEZONE`, `LOG_LEVEL`, `TEMP_DIR`
- Web: `APP_ENABLE_WEB`, `WEB_HOST`, `WEB_PORT`, `WEB_BASE_URL`, `WEB_SESSION_SECRET`
- Bootstrap: `AUTO_CREATE_DB`, `AUTO_MIGRATE`, retry и pool settings

## Рекомендуемые режимы

### Только Telegram

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=false
```

### Только web

```env
APP_ENABLE_TELEGRAM=false
APP_ENABLE_WEB=true
```

### Оба адаптера

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
```

## Docker

`docker-compose.yml` поднимает:

- `db`
- `bot`
- `web`

Запуск:

```bash
docker compose up --build
```

Смысл такой схемы:

- оба adapter service используют один код и одну схему
- bot и web можно деплоить независимо
- создание базы и миграции происходят на старте приложения

## Тестирование

Основные команды:

```bash
pytest -q
python -m compileall app
docker compose config -q
```

Текущий набор тестов покрывает:

- нормализацию категорий
- parser и intent recognition
- ranking semantics
- repository behavior
- runtime configuration
- OCR adapter guard rails
- Telegram mapping/rendering
- web adapter behavior
- interrupt/recovery workflow

## Типовые dev-задачи

### Добавить новый screen action

1. Добавить новый `UserCommand` в нужный adapter mapping при необходимости.
2. Реализовать поведение в `HandleCommandUseCase`.
3. Вернуть `Screen` и опциональный `Effect`.
4. Сначала добавить тесты на уровне application.
5. Если меняется рендеринг, добавить adapter-specific tests.

### Добавить новую storage-backed функцию

1. Расширить application ports, если core нужен новый dependency.
2. Реализовать repository/UoW поведение в PostgreSQL adapter.
3. Добавить Alembic migration.
4. Подключить dependency в `bootstrap/container.py`.

### Добавить новый adapter

1. Переиспользовать `ApplicationFacade`.
2. Маппить inbound events в `UserCommand`.
3. Хранить transport-specific workflow state вне core.
4. Рендерить `Screen` согласно UX адаптера.

## Ожидания по обработке ошибок

- Не проглатывать исключения молча.
- Логировать transport и runtime failures так, чтобы их можно было диагностировать.
- Возвращать короткие локализованные user-facing сообщения.
- После recoverable errors оставлять пользователя в валидном flow state.

## Замечания по деплою

- Использовать реальный `BOT_TOKEN`.
- Перед включением web adapter установить не-default `WEB_SESSION_SECRET`.
- В production использовать secure cookies и HTTPS.
- Для многопользовательского режима тюнить DB pool settings.
- `AUTO_MIGRATE=true` держать только если миграции на старте допустимы вашей deployment policy.
