# Cashback Analyzer

Telegram-бот для анализа и сравнения категорий кэшбэка, которые банки предлагают пользователю. Проект построен как модульная система с отдельным ядром и отдельным Telegram-адаптером.

## Архитектура

- `app/services` — доменное ядро: нормализация категорий, парсинг, OCR, рейтинг, каталог банков.
- `app/db` — persistence layer: модели SQLAlchemy, session factory, repositories.
- `app/handlers`, `app/keyboards`, `app/middlewares`, `app/infrastructure/telegram_*` — внешний Telegram-слой и адаптеры.
- `app/infrastructure/container.py` — композиция приложения без бизнес-логики.
- `alembic/` — миграции PostgreSQL.
- `tests/` — unit, repository, reminder и handler-level тесты.

## Возможности

- регистрация пользователя через `/start`;
- добавление банка из списка или вручную;
- ввод категорий через OCR, ручной текст или шаблон;
- редактирование предпросмотра и пересохранение банка;
- просмотр сохранённых банков;
- рейтинг по категориям и глобальный рейтинг банков;
- запросы вроде `где лучше азс` и `best cashback for fuel`;
- настройки языка и уведомлений;
- история действий и ежемесячные напоминания.

## Переменные окружения

Скопируйте `.env.example` в `.env` и заполните значения:

```env
BOT_TOKEN=
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=cashback_bot
POSTGRES_USER=cashback_user
POSTGRES_PASSWORD=cashback_password
TESSERACT_PATH=tesseract
LANG_DEFAULT=ru
OCR_TIMEOUT=20
MAX_FILE_SIZE=5242880
APP_TIMEZONE=Europe/Moscow
REMINDER_HOUR=10
LOG_LEVEL=INFO
TEMP_DIR=ocr_tmp
```

## Локальный запуск

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

На Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Контейнер `bot` применяет миграции и запускает `python -m app.main`. `docker-compose.yml` поднимает и PostgreSQL, и приложение.

## Тесты

```bash
pytest -q
```

## Что реализовано

- полная замена старой PTB/SQLite-версии на `aiogram 3 + PostgreSQL + SQLAlchemy Async`;
- модульный код с отделённым доменным ядром и Telegram-адаптером;
- Alembic-миграция начальной схемы;
- OCR/NLP/ranking/catalog сервисы;
- inline-навигация и черновик банка через FSM;
- напоминания, локализация RU/EN и история действий;
- Docker/Docker Compose, `.env.example`, README и тесты.
