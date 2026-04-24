# Cashback Analyzer

Cashback Analyzer — это core-first платформа для анализа банковских cashback-предложений с двумя внешними адаптерами:

- Telegram-бот на `aiogram 3`
- веб-приложение на `FastAPI` + SSR mobile-first UI

Продукт хранит и сравнивает актуальные cashback-предложения по картам и банкам пользователя. Он не ведет учет транзакций, реально начисленного cashback, расходов и бюджета.

## Карта документации

- [Обзор продукта](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ru\PRODUCT_OVERVIEW.md)
- [Архитектура](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ru\ARCHITECTURE.md)
- [Разработка и запуск](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ru\DEVELOPMENT.md)
- [Пользовательские сценарии](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ru\USER_FLOWS.md)
- [Web user cases](C:\Users\Kuznetz\Desktop\proga\cashback_bot\docs\ru\WEB_USER_CASES.md)

## Короткое описание

Проект — это кроссплатформенное веб-приложение для управления банковским cashback, которое помогает пользователю собирать данные по картам из разных банков, проверять и редактировать их, а затем получать понятные рекомендации, какой картой платить в конкретной категории, чтобы максимизировать выгоду.

## Бизнес-цель

Система нужна для того, чтобы пользователь быстро понимал, какой картой выгоднее платить в конкретной ситуации.

Это не бухгалтерский продукт и не менеджер личных финансов. Это decision-support продукт для оптимизации cashback:

- собрать предложения разных банков в одном месте
- привести их к сопоставимой форме
- дать пользователю проверить и исправить данные
- выдать практическую рекомендацию по категории или сценарию покупки

В бизнесовом виде это user-centric fintech utility product, который сокращает потери выгоды из-за фрагментации банковских предложений, упрощает работу с ежемесячно меняющимися cashback-категориями и превращает сложные банковские условия в быстрый, полезный и понятный пользовательский опыт на мобильных и десктопных устройствах.

## Что система умеет сейчас

- синхронизирует пользователей через `/start` или Telegram Login
- распознаёт скриншоты банковских приложений через tiered OCR-пайплайн (сначала локальный Tesseract; OpenAI-совместимый vision-LLM используется только как fallback — когда Tesseract вернул пусто или упал по таймауту)
- принимает ручной ввод, однострочник `/quickadd <банк>: кат1 N%, кат2 M%…` и template draft
- нормализует 20+ категорий по RU/EN синонимам и типовым квалификаторам банков («в Городе», «с МТС Premium», «со СберПрайм»), с устойчивостью к опечаткам
- позволяет редактировать draft и уже сохранённые банковские данные
- отвечает на «какая карта для X?» через три входа, объединённые в одном use case:
  - **inline mode** в Telegram (`@cashback_bot <категория>` из любого чата);
  - slash-команда `/best <категория>`;
  - свободный текст («где лучше рестораны»).
- экспонирует тот же запрос как HTTP: `GET /api/best?q=<категория>` для скриптов / мобильных клиентов
- строит лидеров по категориям и глобальный рейтинг банков
- хранит историю действий в `user_logs`
- отправляет ежемесячные напоминания
- запускает Telegram и web адаптеры независимо через feature flags

### Команды Telegram

Бот публикует меню команд через `set_my_commands` на старте:

| Команда | Назначение |
| --- | --- |
| `/start` | Запустить бота. Поддерживает deep-link: `?start=inline_setup` сразу открывает «добавить банк»; `?start=add_bank` / `?start=top` / `?start=help` работают аналогично. |
| `/best <категория>` | Мгновенный ответ «какая карта лучше для X» (тот же путь, что у inline mode). Без аргумента открывает полный рейтинг. |
| `/quickadd Tinkoff: АЗС 5%, Рестораны 3%` | Добавить или заменить банк одной строкой. Разделители: `,`, `;`, `\n` между позициями; `:` / `—` / `-` между банком и позициями. |
| `/banks` | Мои банки. |
| `/top` | Рейтинг. На пустом состоянии показывает CTA «Добавить первый банк». |
| `/settings` | Язык, уведомления. |
| `/help` | Список команд и текстовых интентов. |
| `/home` | Вернуться в главное меню. |
| `/cancel` | Отменить текущий draft и вернуться домой. |

Сообщения об ошибках всегда идут с inline-клавиатурой (Home + контекстный Retry) — пользователь никогда не остаётся на текстовом экране без выхода.

**Rate-limit:** загрузка фото ограничена per-user (всплеск 5, восстановление 1 за 10 сек) чтобы защитить OCR-путь от случайного спама и злоупотреблений. Ручной ввод и slash-команды не ограничены.

## Текущий baseline и продуктовый vision

Текущий baseline уже поддерживает:

- OCR/manual/template ingestion
- preview и редактирование
- редактирование сохраненных банков
- ranking и best-match lookup
- settings, reminders, history
- web и Telegram поверх общего application core

Более широкий vision включает будущие возможности:

- метаданные карты
- лимиты и сроки действия cashback
- более сложную decision logic
- месячные исторические срезы
- более богатую десктопную аналитику и bulk-editing

Эти возможности описаны как roadmap, а не как уже реализованный функционал.

## Кратко об архитектуре

Проект построен как hexagonal/core-first система:

- `app/domain`: чистые доменные модели, enums, ошибки, нормализация, ranking rules
- `app/application`: workflow contracts, use cases, ports, facade
- `app/adapters`: PostgreSQL, OCR (Tesseract + OpenAI-совместимый vision), Telegram, web, scheduler, system clock
- `app/bootstrap`: конфигурация, wiring, startup checks, migrations, runtime

### Распознавание скриншотов

Скриншоты из банковских приложений сложно парсить классическим OCR: сжатый
текст, цветные бейджи, перемешанный RU/EN. Настройка `OCR_PROVIDER` выбирает
движок, который превращает картинку в строки `Категория: N%` для парсера:

- `auto` (по умолчанию, **локаль-приоритет**) — если задан `OPENAI_API_KEY`,
  работает композитный адаптер: **сначала Tesseract** (бесплатно, локально),
  **OpenAI vision вызывается только если Tesseract вернул пусто/таймаут** для
  конкретного скриншота. Без ключа — чистый Tesseract. Так AI-счёт остаётся
  небольшим, а пользователь получает второй шанс на сложных скринах.
- `tesseract` — только `app/adapters/ocr_tesseract`. Подходит для полностью
  offline-развёртываний или жёсткого бюджета.
- `openai` — только `app/adapters/ocr_openai_vision` (без fallback'а). Работает
  с любым OpenAI-совместимым шлюзом: настоящим OpenAI, российскими прокси
  (ProxyAPI, VSEgpt, …), self-hosted Ollama / LM Studio, Together или Groq.
  Меняются только `OPENAI_BASE_URL`, `OPENAI_MODEL` и ключ API.

**Правила эскалации для `auto`:** `errors.ocr_empty` и `errors.ocr_timeout`
запускают AI-fallback; `errors.broken_image` / `errors.file_too_large` нет —
оба движка одинаково упадут, и платить за второй вызов смысла нет.

Адаптер намеренно устойчив: обёртки ```json … ``` от локальных моделей,
текстовые преамбулы перед JSON, проценты вне диапазона, дубликаты категорий,
ошибки rate-limit / таймаута / авторизации / невалидный JSON / отсутствие
`content_type` — всё отображается в те же ключи `errors.*`, что Tesseract, и
UX остаётся одинаковым независимо от того, какой движок ответил.

Транспортно-независимая точка входа в бизнес-логику:

```python
handle_command(user, workflow_state, user_command) -> WorkflowResult
```

И Telegram, и web переводят внешний ввод в `UserCommand`, а затем рендерят возвращенный `Screen`.

## Структура репозитория

```text
app/
  adapters/
    ocr_openai_vision/
    ocr_tesseract/
    postgres/
    scheduler/
    system/
    telegram/
    web/
  application/
    contracts/
    use_cases/
  bootstrap/
  domain/
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

При старте приложение умеет:

- создавать PostgreSQL-базу, если `AUTO_CREATE_DB=true`
- применять миграции Alembic, если `AUTO_MIGRATE=true`
- запускать Telegram и/или web адаптеры по feature flags

## Основные переменные окружения

Полный список есть в [.env.example](C:\Users\Kuznetz\Desktop\proga\cashback_bot\.env.example). Ключевые переменные:

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
- `OCR_PROVIDER` — `auto` (по умолчанию), `openai` или `tesseract`
- `OPENAI_API_KEY` — обязателен для `openai` или `auto` с включённой LLM-моделью
- `OPENAI_BASE_URL` — переопределяет endpoint (ProxyAPI, VSEgpt, Ollama, LM Studio, Together, Groq). Пусто = настоящий OpenAI.
- `OPENAI_MODEL` — по умолчанию `gpt-4o`
- `APP_ENABLE_TELEGRAM`
- `APP_ENABLE_WEB`
- `WEB_BASE_URL`
- `WEB_SESSION_SECRET`

## Режимы запуска

- только Telegram: `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=false`
- только web: `APP_ENABLE_TELEGRAM=false`, `APP_ENABLE_WEB=true`
- оба адаптера: `APP_ENABLE_TELEGRAM=true`, `APP_ENABLE_WEB=true`

Один и тот же application core обслуживает все режимы.

## Краткий user journey

1. Пользователь входит в продукт.
2. Добавляет или обновляет cashback-предложение по банку/карте.
3. Проверяет OCR/manual parsing на preview.
4. Сохраняет актуальные данные.
5. Позже спрашивает «чем платить в этой категории?».
6. Использует ranking output вместо ручного сравнения нескольких банковских приложений.

## Проверки

Полезные команды:

```bash
pytest -q
python -m compileall app
docker compose config -q
```

Текущий staged baseline проходит эти проверки.
