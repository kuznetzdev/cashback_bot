# Operations Runbook (RU)

Оперативное руководство — всё, что нужно знать после мерджа кода и до
следующего деплоя. Архитектурная мотивация — в
[ARCHITECTURE.md](ARCHITECTURE.md); гайд по разработке — в
[DEVELOPMENT.md](DEVELOPMENT.md).

Для полной версии на английском см. [`docs/OPERATIONS.md`](../OPERATIONS.md).

---

## Оглавление

1. [Production-чеклист](#production-чеклист)
2. [Топологии деплоя](#топологии-деплоя)
3. [Webhook-режим](#webhook-режим)
4. [Polling-режим](#polling-режим)
5. [Redis и FSM-состояние](#redis-и-fsm-состояние)
6. [Health, Readiness, Liveness](#health-readiness-liveness)
7. [Prometheus-метрики](#prometheus-метрики)
8. [Структурированные логи](#структурированные-логи)
9. [Backup и миграции БД](#backup-и-миграции-бд)
10. [Настройка OCR-провайдеров](#настройка-ocr-провайдеров)
11. [Security posture](#security-posture)
12. [Процедура upgrade](#процедура-upgrade)
13. [Runbook инцидентов](#runbook-инцидентов)
14. [Capacity planning](#capacity-planning)

---

## Production-чеклист

Перед первым production-деплоем — проверить всё:

### Секреты

- [ ] `BOT_TOKEN` — реальный токен от @BotFather, не placeholder.
- [ ] `WEB_SESSION_SECRET` — `openssl rand -hex 32` (Settings откажется
      стартовать при `APP_ENABLE_WEB=true` и дефолтном значении).
- [ ] `WEBHOOK_SECRET` — тот же генератор. Telegram шлёт в
      `X-Telegram-Bot-Api-Secret-Token`, handler отвечает 403 при
      несовпадении.
- [ ] `METRICS_TOKEN` задан. Без него `/metrics` открыт.
- [ ] `OPENAI_API_KEY`, если `OCR_PROVIDER=openai` или `auto`.
- [ ] `POSTGRES_PASSWORD` не дефолтный.

### Транспорт

- [ ] HTTPS-терминатор (nginx / Caddy / Traefik / ALB) перед web.
- [ ] `WEB_BASE_URL` совпадает с публичным HTTPS URL (без trailing slash).
- [ ] `WEB_SECURE_COOKIES=true`.
- [ ] `CORS_ORIGINS` сужен до конкретных origin'ов фронта — никогда `*`
      в prod.

### Состояние

- [ ] `FSM_STORAGE=redis` + `REDIS_URL` указывает на persistent Redis.
- [ ] Postgres бэкапится по расписанию (см.
      [Backup](#backup-и-миграции-бд)).
- [ ] Политика `AUTO_MIGRATE` явно задана — `true` для быстрых деплоев,
      `false` для ручного контроля.

### Наблюдаемость

- [ ] Prometheus (или совместимый) собирает `/metrics` с bearer-токеном.
- [ ] Агрегатор логов (Loki, Elastic, CloudWatch, Datadog) читает stdout
      контейнера — в prod это уже JSON.
- [ ] Алерты на:
  - `/health` не-200 дольше 60 секунд.
  - `cashback_bot_requests_total{status="error"}` выше порога.
  - `cashback_bot_active_users_total` упал до нуля в рабочее время.

### Safety net

- [ ] Предыдущий образ тегнут для быстрого отката.
- [ ] Пул соединений БД размерен правильно: `DB_POOL_SIZE × replicas <
      Postgres max_connections`.
- [ ] Таймзона напоминаний (`APP_TIMEZONE`) проверена.

---

## Топологии деплоя

### Один контейнер (dev или маленький деплой)

```yaml
services:
  db: postgres:16-alpine
  redis: redis:7-alpine
  bot:
    image: cashback:latest
    environment:
      APP_ENABLE_TELEGRAM: "true"
      APP_ENABLE_WEB: "true"
      FSM_STORAGE: redis
      REDIS_URL: redis://redis:6379/0
      WEBHOOK_ENABLED: "false"
```

Плюс: просто. Минус: одна реплика — если процесс упал, бот лежит.

### Одна реплика с webhook

Тот же образ, но:

```yaml
environment:
  APP_ENABLE_TELEGRAM: "true"
  APP_ENABLE_WEB: "true"
  WEBHOOK_ENABLED: "true"
  WEBHOOK_PATH: /bot/webhook
  WEBHOOK_SECRET: ${WEBHOOK_SECRET}
  WEB_BASE_URL: https://your-domain.com
ports:
  - "8080:8080"
```

Плюс: Telegram пушит апдейты только когда они есть — без idle-polling
трафика.

### Несколько web-реплик + одна bot-реплика

**Polling-цикл не должен идти на нескольких репликах** (Telegram
сериализует апдейты одному consumer). Два варианта:

1. **Webhook + N web-реплик.** Каждая реплика запускает web с `/bot/webhook`;
   Telegram балансирует по TCP. FSM должен быть в Redis, иначе mid-wizard
   пользователи попадают в разные реплики и теряют состояние.
2. **Polling-бот + N web-реплик.** Одна отдельная реплика с
   `APP_ENABLE_TELEGRAM=true` (polling); остальные — только web. Бот —
   единая точка отказа, но web масштабируется независимо.

### Раздельные bot + web (Docker Compose)

Поставляемый `docker-compose.yml`:

```yaml
bot:
  environment:
    APP_ENABLE_TELEGRAM: "true"
    APP_ENABLE_WEB: "false"
web:
  environment:
    APP_ENABLE_TELEGRAM: "false"
    APP_ENABLE_WEB: "true"
  ports: ["8080:8080"]
```

Можно рестартить web, не дропая polling-подключение к Telegram.

---

## Webhook-режим

### Активация

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=true
WEBHOOK_PATH=/bot/webhook
WEBHOOK_SECRET=<openssl rand -hex 32>
WEB_BASE_URL=https://your-domain.com
```

На старте `runtime._run_webhook_adapter` вызывает:

```python
await bot.set_webhook(
    url=f"{WEB_BASE_URL}{WEBHOOK_PATH}",
    secret_token=WEBHOOK_SECRET,
    drop_pending_updates=True,
)
```

На shutdown: `bot.delete_webhook()`.

### Проверка

```bash
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | jq
```

`last_error_date` и `last_error_message` — признак, что Telegram не
достучался. Частые причины:

| Ошибка | Фикс |
|---|---|
| `SSL handshake failed` | Проблема с TLS — цепочка, SNI, срок действия. |
| `Wrong response: HTTPS url must be provided` | `WEB_BASE_URL` начинается с `http://`. Поставить `https://`. |
| `Unknown certificate authority` | Self-signed — использовать Let's Encrypt или залить сертификат через `setWebhook`. |
| Растёт `pending_update_count` | Handler возвращает не-200. Проверить `/health` и свежие логи. |

### Возврат к polling

```env
WEBHOOK_ENABLED=false
```

На следующем старте polling сам вызовет `bot.delete_webhook()`.

---

## Polling-режим

Проще, но не масштабируется. Для dev и личных деплоев.

```env
APP_ENABLE_TELEGRAM=true
WEBHOOK_ENABLED=false
```

Polling обрабатывает:

- **`TelegramUnauthorizedError`** — critical log, re-raise. Бот падает —
  orchestrator перезапустит (бесполезно без фикса токена, зато заметно).
- **`TelegramNetworkError` / `TelegramServerError`** — warning, sleep
  `TELEGRAM_RETRY_DELAY`, retry.

---

## Redis и FSM-состояние

### Зачем

`FSM_STORAGE=memory` теряет состояние на любом рестарте. Пользователи
посреди wizard'а («Выбор способа → Фото → [crash] → ???») попадают на
home без ошибки. Redis это переживает.

### Настройка

```env
FSM_STORAGE=redis
REDIS_URL=redis://redis:6379/0
```

Ключи с префиксом `cashback_fsm:`. Можно делить Redis с другими приложениями,
если они не используют этот префикс.

### Память

Aiogram Redis storage хранит:

- FSM state на пользователя: ~сотни байт.
- FSM data на пользователя: `WorkflowState` в JSON, обычно < 2 КБ.

Для N активных пользователей (активный = начал wizard за 14 дней):
~N × 3 КБ. 100 тыс. → ~300 МБ.

### Мониторинг

```bash
redis-cli -u $REDIS_URL INFO memory
redis-cli -u $REDIS_URL DBSIZE
redis-cli -u $REDIS_URL --scan --pattern 'cashback_fsm:*' | wc -l
```

---

## Health, Readiness, Liveness

### `GET /health`

```json
{
  "status": "ok",
  "db": "ok",
  "telegram": "ok",
  "ocr": {"primary": "auto", "status": "ok"},
  "version": "<git-sha>"
}
```

- **DB-проба:** `SELECT 1` с таймаутом 2 с.
- **Telegram-проба:** `bot.get_me()` с таймаутом 3 с.
- **`n/a`:** проба не подключена — **не** триггерит degraded.

HTTP: `200` при `ok`, `503` при `degraded`.

### Kubernetes probe

```yaml
readinessProbe:
  httpGet: { path: /health, port: 8080 }
  periodSeconds: 10
  failureThreshold: 3
livenessProbe:
  httpGet: { path: /health, port: 8080 }
  periodSeconds: 30
  failureThreshold: 5
```

### Docker HEALTHCHECK

В образе уже:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1
```

---

## Prometheus-метрики

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8080/metrics
```

При пустом `METRICS_TOKEN` endpoint открыт. **В prod не оставлять так.**

### Справочник метрик

| Метрика | Тип | Лейблы | Смысл |
|---|---|---|---|
| `cashback_bot_requests_total` | Counter | `handler`, `status` | Количество вызовов handler'а |
| `cashback_bot_request_duration_seconds` | Histogram | `handler` | Latency handler'а |
| `cashback_bot_ocr_calls_total` | Counter | `provider`, `result` | OCR-вызовы |
| `cashback_bot_active_users_total` | Gauge | — | Уникальные user_id с момента старта |

### Идеи панелей Grafana

- **Latency handler** — `histogram_quantile(0.95, rate(cashback_bot_request_duration_seconds_bucket[5m])) by (handler)`.
- **Error rate** — `sum(rate(cashback_bot_requests_total{status="error"}[5m])) / sum(rate(cashback_bot_requests_total[5m]))`.
- **OCR mix** — `sum(rate(cashback_bot_ocr_calls_total[1h])) by (provider)`.

### Алерт-пороги (предложения)

| Rule | Когда срабатывать |
|---|---|
| `ErrorRate5xx` | `error_rate > 0.05` за 5 мин |
| `HighLatency` | `p95 > 3s` на любом handler 5 мин |
| `OCRFailures` | `rate(cashback_bot_ocr_calls_total{result="error"}[5m]) > 0.1` |
| `HealthDegraded` | `/health` 503 за 1 мин |

---

## Структурированные логи

### Формат

Prod (`LOG_LEVEL != DEBUG`): JSON-линии.

```json
{
  "event": "telegram_update",
  "level": "info",
  "timestamp": "2026-04-24T12:34:56.789012Z",
  "correlation_id": "a1b2c3d4",
  "user_id": 12345,
  "update_type": "message",
  "handler": "on_start",
  "elapsed_ms": 42.7,
  "status": "ok"
}
```

Dev (`LOG_LEVEL=DEBUG`): цветной `ConsoleRenderer`.

### Поля для индексации

- `correlation_id` (primary key одного трейса)
- `user_id`
- `handler`
- `status`
- `level`

---

## Backup и миграции БД

### Стратегия backup

```bash
pg_dump --host=$POSTGRES_HOST --user=$POSTGRES_USER --format=custom \
        --file=/backups/cashback-$(date +%Y%m%d).pgdump cashback_bot
```

Держите минимум 7 дневных + 4 недельных + 12 месячных. Тестируйте
restore ежемесячно.

### Миграции на boot

`AUTO_MIGRATE=true` вызывает `alembic upgrade head` при старте, retries
до `MIGRATION_MAX_ATTEMPTS × MIGRATION_RETRY_DELAY` секунд.

### Миграции отдельным шагом

Для ops-команд покрупнее: `AUTO_MIGRATE=false` + `alembic upgrade head`
как pre-deploy Job. Раскатывать образ только после успеха job.

### Rollback

```bash
alembic downgrade -1
alembic downgrade <rev>
alembic current
```

### Текущая цепочка миграций

1. `20260306_0001_initial.py` — базовая схема.
2. `20260311_0002_platform_identity.py` — split telegram → `user_identities`.
3. `20260424_0003_performance_indexes.py` — покрывающие индексы.

---

## Настройка OCR-провайдеров

### Только Tesseract

```env
OCR_PROVIDER=tesseract
TESSERACT_PATH=tesseract
OCR_TIMEOUT=20
```

Без outbound-трафика и AI-счета.

### OpenAI Vision

```env
OCR_PROVIDER=openai
OPENAI_API_KEY=<key>
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=
OPENAI_VISION_TIMEOUT=60
OPENAI_VISION_MAX_TOKENS=1024
```

### Совместимые шлюзы

| Шлюз | `OPENAI_BASE_URL` | Примечание |
|---|---|---|
| Реальный OpenAI | (пусто) | Лучшее качество, сложно из РФ. |
| ProxyAPI | `https://api.proxyapi.ru/openai/v1` | Русский прокси. |
| VSEgpt | `https://api.vsegpt.ru/v1` | Аналог. |
| Ollama | `http://localhost:11434/v1` | Self-hosted, нужна vision-модель. |
| LM Studio | `http://localhost:1234/v1` | Аналог. |
| Together.ai | `https://api.together.xyz/v1` | Дешёвый vision. |

### Composite (рекомендуется)

```env
OCR_PROVIDER=auto
OPENAI_API_KEY=<key>
```

Tesseract первым, OpenAI — только на empty/timeout.

---

## Security posture

### Pre-flight (Settings validator)

`Settings` откажется конструироваться при `APP_ENABLE_WEB=true` и
дефолтном `WEB_SESSION_SECRET`. На старте увидите `ValueError` — это
ожидаемое поведение, не баг.

### TLS

- HTTPS терминируется на reverse-proxy. Python слушает plain HTTP:8080.
- `WEB_SECURE_COOKIES=true` — сессионные cookie только по HTTPS.
- Uvicorn `proxy_headers=True` — читает `X-Forwarded-*`.

### Rate-лимиты

| Где | Лимит | Override |
|---|---|---|
| Telegram msg/callback на пользователя | 30 / мин (burst 30) | Hardcoded в `TelegramDependencies` |
| Telegram фото на пользователя | 5 burst, refill 1 / 10 с | Hardcoded в `runtime.py` |
| Public `/api/*` на IP | `API_RATE_LIMIT_PER_MINUTE` (60) | Env |

In-process limiter — для multi-replica добавьте edge-ограничитель.

### Ротация секретов

```bash
NEW_SECRET=$(openssl rand -hex 32)
# Обновить в Vault / AWS Secrets Manager / k8s Secret
kubectl rollout restart deployment/cashback-web
```

Для `WEBHOOK_SECRET` дополнительно:

```bash
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://your-domain.com/bot/webhook" \
  -d "secret_token=${NEW_SECRET}" \
  -d "drop_pending_updates=false"
```

Затем рестартить bot-сервис.

---

## Процедура upgrade

### Minor (багфикс, без схемы)

1. Задеплоить новый образ в staging.
2. Smoke-тест `/health` + `/metrics`.
3. Мануально пройти happy-path.
4. Тегнуть текущий prod-образ как `cashback:previous`.
5. Раскатить prod.
6. Посмотреть error rate + latency 10 мин.
7. При подозрениях — rollback на `cashback:previous`.

### Major (новая схема, env)

1. Review миграции — есть ли нормальный downgrade?
2. Обновить `.env.example`.
3. Обновить пороги алертов, если изменились лейблы.
4. Раскатить в staging с `AUTO_MIGRATE=true`, проверить.
5. Prod: запустить миграцию отдельным Job **до** раскатки app.
6. Раскатить app.
7. Следить за latency изменённых запросов через `/metrics`.

---

## Runbook инцидентов

### «Бот не отвечает на /start»

**Проверить** `/health` → `telegram`. Если `error`:

1. `curl "https://api.telegram.org/bot${BOT_TOKEN}/getMe"` — 401 → плохой
   токен, timeout → DNS/firewall.
2. В webhook: `getWebhookInfo` → `last_error_message`.
3. В polling: искать `TelegramUnauthorizedError` / `TelegramNetworkError`.

### «OCR всегда падает»

1. `/metrics` → `cashback_bot_ocr_calls_total{result="error"}` растёт?
2. Лог-поиск: `event="OCR error"` → типично видно корень.
3. Попробовать `OCR_PROVIDER=tesseract` для изоляции.

### «Пользователи теряют wizard-состояние»

`FSM_STORAGE=memory` + рестарт. Переключить на Redis. Если уже Redis:

1. `redis-cli ping` из bot-контейнера — доступен?
2. `redis-cli INFO memory` — не OOM-killed?

### «/health возвращает 503»

1. Тело ответа показывает, какая проба упала.
2. `db: error` → Postgres liveness, пул, credentials.
3. `telegram: error` → см. первый пункт выше.

### «Latency spike на /best»

1. `/metrics` → `histogram_quantile(0.95, ...)` на `on_best_command`.
2. Ranking cache может быть холодным — после всплеска `invalidate()`
   ожидайте transient spike, пока кеш прогревается.
3. Проверить Postgres slow queries через `pg_stat_statements`.
4. Если затрагивается bulk JOIN, убедиться, что миграция
   `20260424_0003` применена (`ix_cashback_items_bank_category`).

### «Webhook возвращает 403»

1. `getWebhookInfo` → `last_error_message`.
2. Сверить `WEBHOOK_SECRET` в env с тем, что передано в `setWebhook`.
   При расхождении перезвать `setWebhook`.
3. Проверить, что reverse-proxy не стрипает заголовок
   `X-Telegram-Bot-Api-Secret-Token` (`proxy_pass_header` в nginx).

### «Напоминание не доставлено»

1. Лог: `event="reminder dispatched", user_id=<N>` — была попытка?
2. Если нет: `event="reminder skipped"` (уже отправлено в этом месяце)
   или `user.notifications_enabled=false`.
3. Если попытка упала: `event="Reminder delivery failed"` — обычно
   403 (пользователь заблокировал бот) или 400 (битый chat_id).

---

## Capacity planning

### Размер (bot + web в одном контейнере)

| Активных | CPU | RAM | Заметки |
|---|---|---|---|
| < 1К | 0.5 core | 512 МБ | Tesseract — пик CPU при OCR-всплесках |
| 1К – 10К | 1 core | 1 ГБ | Следить за памятью Redis |
| 10К – 100К | 2 core, подумать о split web/bot | 2 ГБ | N web-реплик, 1 polling bot |
| > 100К | Webhook обязателен, N web-реплик | 2+ ГБ на реплику | Redis + Postgres — bottleneck |

### Sizing DB-пула

`DB_POOL_SIZE × replicas` должен быть ощутимо меньше Postgres
`max_connections` (default 100). При N реплик с пулом 10 оставьте хотя
бы `100 - N*10` соединений под admin / миграции / мониторинг.

### Telegram Bot API лимиты

- 30 сообщений в секунду глобально на бота.
- ~20 сообщений в минуту в один чат.

Превышение → 429. `TelegramReminderSender` шлёт напоминания по порядку
user_id — для больших баз reminder-loop становится long-running-таской.

### Стоимость OpenAI

Для GPT-4o в момент написания: ~0.5 цента за изображение. 10К загрузок/месяц
с 20% AI-fallback → ~$10/месяц.

---

## Приложение: пример nginx reverse-proxy

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location /bot/webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_pass_request_headers on;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Request-Id $request_id;
    }
}
```

### Prometheus scrape config

```yaml
scrape_configs:
  - job_name: cashback
    scheme: https
    metrics_path: /metrics
    bearer_token: ${METRICS_TOKEN}
    static_configs:
      - targets: ['your-domain.com']
    scrape_interval: 30s
```
