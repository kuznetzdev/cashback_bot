# Development гайд

Runbook для разработчиков `cashback_analyzer`. Охватывает локальный setup,
типовые задачи, тестовую топологию и паттерны, которым ожидаемо следовать.

Мотивация архитектуры — [`ARCHITECTURE.md`](ARCHITECTURE.md). Production-деплой —
[`OPERATIONS.md`](OPERATIONS.md). Полный справочник env-переменных —
[`CONFIGURATION.md`](CONFIGURATION.md). Английская версия —
[`docs/DEVELOPMENT.md`](../DEVELOPMENT.md).

---

## Требования

| Инструмент | Версия | Комментарий |
|---|---|---|
| Python | 3.11+ (рекомендуется 3.12) | `python --version` |
| PostgreSQL | 15+ | Опционально локально — тесты используют SQLite in-memory |
| Redis | 7.x | Опционально — нужен для `FSM_STORAGE=redis` |
| Tesseract OCR | 5.x с `rus` language pack | Windows: <https://github.com/UB-Mannheim/tesseract/wiki> — отметить «Russian». Unix: `apt install tesseract-ocr tesseract-ocr-rus` |
| Docker | latest stable | Опционально, compose-ready |
| `openssl` или аналог | — | Для генерации секретов: `openssl rand -hex 32` |

---

## Локальный setup

```bash
# 1. Клонирование
git clone <repo-url>
cd cashback_bot

# 2. Виртуальное окружение
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Unix
source .venv/bin/activate

# 3. Зависимости
pip install -r requirements.txt

# 4. Скопировать пример env
cp .env.example .env

# 5. Открыть .env и минимум задать:
#    - BOT_TOKEN=<реальный токен>
#    - POSTGRES_* (или DATABASE_URL для SQLite)
#    - WEB_SESSION_SECRET (если APP_ENABLE_WEB=true)
#    - OPENAI_API_KEY (опционально, для OCR fallback)

# 6. Запуск
python -m app.main
```

### Первичный troubleshooting

| Симптом | Фикс |
|---|---|
| `RuntimeError: BOT_TOKEN is not configured` | Задать `BOT_TOKEN` в `.env`, не placeholder `123456:TEST_TOKEN`. |
| `ValueError: WEB_SESSION_SECRET must be changed...` | `APP_ENABLE_WEB=true` требует нон-дефолтный секрет. `openssl rand -hex 32`. |
| `connection refused` на старте | PostgreSQL не запущен или `POSTGRES_HOST` неверный. `docker compose up db -d`. |
| `pytesseract.pytesseract.TesseractNotFoundError` | Бинарь tesseract не в `$PATH`. Задать `TESSERACT_PATH=/full/path/to/tesseract`. |
| OCR возвращает мусор | Установить русский language pack (`tesseract-ocr-rus` или «Russian» в Windows-инсталляторе). |

---

## Runtime-последовательность

Управляется `app/bootstrap/runtime.py::run_app()`:

1. **Загрузка settings.** `Settings()` читает `.env` + env, запускает
   field-валидаторы и model-validator (fail-fast на опасных комбинациях
   типа `APP_ENABLE_WEB=true` + дефолтный session secret).
2. **Настройка логгирования.** structlog-pipeline (JSON в prod, Console в dev).
3. **Валидация startup.** `_validate_startup_settings` — обе адаптера
   не выключены, токен бота валидный, session secret, OCR-провайдер.
4. **Ожидание БД.** Ретраи `SELECT 1` до `DB_CONNECT_MAX_ATTEMPTS`.
5. **Миграции.** `alembic upgrade head` при `AUTO_MIGRATE=true`.
6. **Сборка DI-контейнера.** `build_core_container(settings, metrics)` →
   `build_application_facade(core, reminder_sender)`.
7. **Старт адаптеров.** Каждый — `asyncio.Task`.
8. **Ожидание shutdown или failure.** Первая завершившаяся task (или SIGTERM)
   побеждает; остальные отменяются в `finally`.

Graceful shutdown: сигналы ставят `asyncio.Event`, которую
`_await_until_shutdown_or_failure` awaits вместе с task'ами адаптеров.

---

## Режимы запуска

Все четыре комбинации `APP_ENABLE_TELEGRAM` × `APP_ENABLE_WEB`
поддерживаются:

### Только Telegram

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=false
```

Стандартный bot-деплой. Polling по умолчанию.

### Только web (с Telegram Login)

```env
APP_ENABLE_TELEGRAM=false
APP_ENABLE_WEB=true
WEB_ENABLE_TELEGRAM_AUTH=true
BOT_TOKEN=<нужен для Telegram Login widget>
```

### Полный гибрид (polling)

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=false
```

### Полный гибрид (webhook — production)

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=true
WEBHOOK_SECRET=<strong random>
WEB_BASE_URL=https://your-domain.com
```

### Чистый web без Telegram

```env
APP_ENABLE_TELEGRAM=false
APP_ENABLE_WEB=true
WEB_ENABLE_TELEGRAM_AUTH=false
```

---

## Типовые задачи

### Добавить use case

1. **Набросать интерфейс.** Что принимает, что возвращает? Предпочтительно
   один публичный `execute(**kwargs)`.
2. **Нужен новый port?** Если use case читает/пишет что-то, что не покрыто
   текущими `*RepositoryPort`, добавить Protocol в
   `app/application/contracts/ports.py`.
3. **Сначала тест.** В `tests/test_<use_case>.py`. Используй фикстуры
   `uow_factory` и `store` из `conftest.py`. Assert'ы на `store.banks`,
   `store.logs` и т.д.
4. **Класс.** Один файл в `app/application/use_cases/`. Принимает
   `uow_factory: Callable[[], UnitOfWorkPort]` через `__init__`.
5. **Реализация persistence** в `app/adapters/postgres/repositories.py`,
   если был добавлен port method.
6. **Wiring в контейнере.** `app/bootstrap/container.py`.
7. **Expose через facade**, если адаптеры зовут —
   `app/application/facade.py`.
8. **Вызов из workflow / router.** `app/application/use_cases/handle_command.py`
   или напрямую из handler в `app/adapters/telegram/router.py` /
   `app/adapters/web/app.py`.

#### Подсказка: инвалидация кеша

Если use case пишет то, что `RankingSnapshotUseCase` читает (банки,
cashback items) — дёрни `RankingSnapshotUseCase.invalidate(user_id)`
после `uow.commit()`. Примеры: `SaveBankDraftUseCase`, `DeleteBankUseCase`,
`DeleteCategoryUseCase`.

### Добавить локализационную строку

1. Добавить `your.new.key` в **оба** `app/locales/ru.json` и
   `app/locales/en.json`.
2. Использовать как `localizer.t("your.new.key", language)`.
   Интерполяция: `localizer.t("messages.hello", language, {"name": user.display_name})`.
3. Error-ключи: префикс `errors.*`. Router-recovery
   (`_OCR_RETRYABLE_KEYS`) смотрит именно на него.

Missing-ключи fallback-ают молча (возвращают сам ключ), но CI не ловит
рассинхрон — держите оба каталога в синхроне руками.

### Добавить транспортный адаптер

Следуя паттерну `app/adapters/telegram` и `app/adapters/web`:

1. **Переиспользовать `ApplicationFacade`** как единый entry-point —
   не строить параллельный фасад. Прокинуть через dataclass зависимостей.
2. **Мапить входящие события в `UserCommand`.**
3. **Session-state — вне ядра.** Используй FSM aiogram, FastAPI-сессии,
   что даст транспорт.
4. **Рендерить `Screen` + `Action` — в UX транспорта.**
5. **Не импортировать другие адаптеры.** Общее — в
   `app/adapters/<name>.py`, не внутри соседнего пакета.

### Добавить Alembic-миграцию

```bash
alembic revision --autogenerate -m "описание"
# Проверить сгенерированный файл — autogenerate не идеален
alembic upgrade head    # применить локально
# Закоммитить вместе: изменение модели + миграцию
```

---

## Тестирование

### Быстрый справочник

```bash
python -m pytest -q                                           # весь suite
python -m pytest tests/test_middleware.py -q                  # один файл
python -m pytest tests/test_X.py::test_name -q                # один тест
python -m pytest -s                                           # с выводом
python -m pytest -x                                           # стоп на падении
python -m pytest -v                                           # verbose
```

### Топология

| Слой | Скорость | Зависимости | Количество (прим.) |
|---|---|---|---|
| Domain unit | <10 мс | Pure Python | ~60 |
| Application unit | <50 мс | `InMemoryUnitOfWork` | ~120 |
| Adapter (postgres) | ~300 мс | `sqlite+aiosqlite` через `StaticPool` | ~15 |
| Web | ~500 мс | `httpx.AsyncClient` + `ASGITransport` | ~40 |
| Telegram router | ~200 мс | `MagicMock` bot, реальный router | ~20 |
| Architecture boundary | <50 мс | AST walk | ~5 |
| Scenario regressions | ~500 мс | Полный facade + in-memory UoW | ~20 |

**Baseline:** 379 тестов, прогон ~1–2 мин на Windows, ~40 с на Unix.

### Важные фикстуры (`tests/conftest.py`)

| Фикстура | Что даёт |
|---|---|
| `store` | `InMemoryStore` dataclass — assert'ить напрямую |
| `uow_factory` | Zero-arg callable, возвращающий свежий `InMemoryUnitOfWork` |
| `dummy_ocr` | `DummyOCR` с настраиваемым `value` |

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
```

### Что крутит CI

```bash
python -m pytest -q
python -m compileall app tests
docker compose config -q
```

---

## Стиль кода

- **Без emoji**, если не попросили явно. Лог-строки, docstring'и, комментарии —
  ASCII, исключение только для user-facing локалей.
- **Комментарии объясняют ПОЧЕМУ, не ЧТО.**
- **Без многоабзацных docstring'ов на private-хелперах.** Максимум одна строка.
- **`structlog.get_logger(__name__)`.** Не stdlib `logging`.
- **Pydantic v2 идиомы.** `Field(default=..., alias="ENV_NAME")`,
  `model_validator(mode="after")`.
- **Type hints на каждой публичной функции.** `-> SomeType:`.
  `from __future__ import annotations` в шапке каждого файла.

---

## Deployment notes

Полный чеклист — [OPERATIONS.md](OPERATIONS.md).

TL;DR:

- Сгенерировать `WEB_SESSION_SECRET`, `WEBHOOK_SECRET`, `METRICS_TOKEN`.
- `WEB_SECURE_COOKIES=true` за HTTPS.
- `FSM_STORAGE=redis` в prod; memory — только dev.
- `AUTO_MIGRATE`: true по умолчанию; в prod-средах с ручным контролем — false.
- Мониторить `/metrics`, алерт на падающий `cashback_bot_active_users_total`
  или рост `cashback_bot_requests_total{status="error"}`.

---

## Глоссарий

| Термин | Значение |
|---|---|
| **UoW** | Unit of Work — SQLAlchemy session в async-context-manager |
| **Facade** | `ApplicationFacade` — единый entry-point для адаптеров |
| **Port** | `Protocol`-класс в `app/application/contracts/ports.py` |
| **Adapter** | Конкретная реализация port'а |
| **Screen** | Транспорт-нейтральное описание экрана |
| **Effect** | Запрос side-effect от use case |
| **WorkflowState** | Per-user FSM-состояние |
| **UserCommand** | Adapter-level input: `{name, payload}` |
| **WorkflowResult** | Use-case output |
| **Correlation ID** | Короткий uuid per request/update для трейсинга |
