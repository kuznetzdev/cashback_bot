# Operations Runbook

This document is the **operator's manual** — everything you need to know
after code is merged and before the next deploy. Architecture rationale
lives in [ARCHITECTURE.md](ARCHITECTURE.md); contributing workflow lives
in [DEVELOPMENT.md](DEVELOPMENT.md); env reference lives in
[CONFIGURATION.md](CONFIGURATION.md).

---

## Table of Contents

1. [Production Checklist](#production-checklist)
2. [Deployment Topologies](#deployment-topologies)
3. [Webhook Mode](#webhook-mode)
4. [Polling Mode](#polling-mode)
5. [Redis & FSM State](#redis--fsm-state)
6. [Health, Readiness & Liveness](#health-readiness--liveness)
7. [Prometheus Metrics](#prometheus-metrics)
8. [Structured Logging](#structured-logging)
9. [Database Backups & Migrations](#database-backups--migrations)
10. [OCR Provider Setup](#ocr-provider-setup)
11. [Security Posture](#security-posture)
12. [Upgrade Procedure](#upgrade-procedure)
13. [Incident Runbook](#incident-runbook)
14. [Capacity Planning](#capacity-planning)

---

## Production Checklist

Before first production deploy, verify every box:

### Secrets

- [ ] `BOT_TOKEN` is a real token from @BotFather, not the placeholder.
- [ ] `WEB_SESSION_SECRET` generated via `openssl rand -hex 32` (Settings
      will refuse to start with the default placeholder when
      `APP_ENABLE_WEB=true`).
- [ ] `WEBHOOK_SECRET` generated (same generator). Telegram sends this back
      in `X-Telegram-Bot-Api-Secret-Token`; the handler 403s on mismatch.
- [ ] `METRICS_TOKEN` generated. Without it, `/metrics` is open.
- [ ] `OPENAI_API_KEY` set if using `OCR_PROVIDER=openai` or `auto`.
- [ ] `POSTGRES_PASSWORD` changed from the default.

### Transport

- [ ] HTTPS terminator (nginx / Caddy / Traefik / ALB) in front of the
      web service.
- [ ] `WEB_BASE_URL` matches the public HTTPS URL (no trailing slash).
- [ ] `WEB_SECURE_COOKIES=true`.
- [ ] `CORS_ORIGINS` narrowed to the exact frontend origin(s) — never `*`
      in production.

### State

- [ ] `FSM_STORAGE=redis` + `REDIS_URL` pointed at a persistent Redis.
- [ ] Postgres is backed up on a schedule (see
      [Database Backups](#database-backups--migrations)).
- [ ] `AUTO_MIGRATE` policy explicitly set — `true` for fast deploys,
      `false` when you want manual control.

### Observability

- [ ] Prometheus / compatible scraper configured to hit `/metrics` with
      the bearer token.
- [ ] Log aggregator (Loki, Elastic, CloudWatch, Datadog) ingesting the
      container's stdout — the output is already JSON in production.
- [ ] Alerting on:
  - `/health` non-200 for more than 60 seconds.
  - `cashback_bot_requests_total{status="error"}` above a threshold.
  - `cashback_bot_active_users_total` dropping to zero mid-day.

### Safety nets

- [ ] Previous image tagged for quick rollback.
- [ ] DB connection pool sized appropriately (`DB_POOL_SIZE` × replicas <
      Postgres `max_connections`).
- [ ] Reminder dispatch timezone (`APP_TIMEZONE`) verified — wrong TZ
      means reminders fire at unintended hours.

---

## Deployment Topologies

### Single-container (dev or tiny deployment)

```yaml
# docker-compose.yml (trimmed)
services:
  db: postgres:16-alpine
  redis: redis:7-alpine
  bot:
    image: cashback:latest
    environment:
      APP_ENABLE_TELEGRAM: "true"
      APP_ENABLE_WEB: "true"        # optional — enables /health and /metrics
      FSM_STORAGE: redis
      REDIS_URL: redis://redis:6379/0
      WEBHOOK_ENABLED: "false"      # polling mode
```

Pros: simple, one container to reason about.
Cons: a single replica. If the process crashes, bot is down.

### Single-replica with webhook

Same image, but:

```yaml
environment:
  APP_ENABLE_TELEGRAM: "true"
  APP_ENABLE_WEB: "true"
  WEBHOOK_ENABLED: "true"
  WEBHOOK_PATH: /bot/webhook
  WEBHOOK_SECRET: ${WEBHOOK_SECRET}
  WEB_BASE_URL: https://your-domain.com
ports:
  - "8080:8080"   # expose the web port so Telegram can reach /bot/webhook
```

Pros: Telegram pushes updates only when they exist — zero idle polling
traffic. A proper TLS terminator in front handles SNI + certificates.

### Multiple web replicas + single bot replica

The **bot's polling loop must not run on multiple replicas** (Telegram
serializes updates to one consumer; the second will starve). Two shapes:

1. **Webhook + N web replicas.** Every replica runs the web adapter with
   the `/bot/webhook` endpoint; Telegram load-balances naturally across
   whichever replica it hits. FSM state must be in Redis (otherwise
   mid-wizard users get different replicas and lose state).
2. **Polling bot + N web replicas.** One dedicated replica runs
   `APP_ENABLE_TELEGRAM=true` (polling); the rest run
   `APP_ENABLE_TELEGRAM=false, APP_ENABLE_WEB=true`. The polling replica
   is a single point of failure for the Telegram adapter, but the web
   adapter scales independently.

### Split bot + web services (Docker Compose)

The shipped `docker-compose.yml`:

```yaml
bot:
  environment:
    APP_ENABLE_TELEGRAM: "true"
    APP_ENABLE_WEB: "false"     # bot-only container
web:
  environment:
    APP_ENABLE_TELEGRAM: "false"  # web-only container
    APP_ENABLE_WEB: "true"
  ports: ["8080:8080"]
```

Pros: you can restart the web service without dropping the bot polling
connection, and vice versa.

---

## Webhook Mode

### Activation

```env
APP_ENABLE_TELEGRAM=true
APP_ENABLE_WEB=true
WEBHOOK_ENABLED=true
WEBHOOK_PATH=/bot/webhook
WEBHOOK_SECRET=<openssl rand -hex 32>
WEB_BASE_URL=https://your-domain.com
```

On startup `runtime._run_webhook_adapter` calls:

```python
await bot.set_webhook(
    url=f"{WEB_BASE_URL}{WEBHOOK_PATH}",
    secret_token=WEBHOOK_SECRET,
    drop_pending_updates=True,
)
```

And on shutdown: `bot.delete_webhook()`.

### Verification

```bash
# 1. Does Telegram agree?
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | jq

# Expected shape:
# {
#   "ok": true,
#   "result": {
#     "url": "https://your-domain.com/bot/webhook",
#     "has_custom_certificate": false,
#     "pending_update_count": 0,
#     "max_connections": 40,
#     "ip_address": "..."
#   }
# }
```

`last_error_date` and `last_error_message` appear in the response body if
Telegram has recently failed to reach your endpoint. Common causes:

| Error | Fix |
|---|---|
| `SSL handshake failed` | TLS certificate issue — check chain, SNI, expiry. |
| `Wrong response from the webhook: HTTPS url must be provided` | `WEB_BASE_URL` starts with `http://`. Use `https://`. |
| `Unknown certificate authority` | Self-signed cert — use Let's Encrypt or upload the cert via `setWebhook`. |
| `pending_update_count` keeps growing | Your handler returns non-200. Check `/health` and recent logs. |

### Switching back to polling

```env
WEBHOOK_ENABLED=false
```

On next restart the polling adapter calls `bot.delete_webhook()` before it
starts listening, so no manual API call is needed.

---

## Polling Mode

Simpler but doesn't scale horizontally. Use in dev, personal deployments,
or when a public HTTPS endpoint is inconvenient.

```env
APP_ENABLE_TELEGRAM=true
WEBHOOK_ENABLED=false
```

The polling loop (`_run_polling_with_retry`) handles:

- **`TelegramUnauthorizedError`** — logs critical and re-raises. Bot exits
  non-zero so the orchestrator restarts (pointless without a token fix,
  but at least it's visible).
- **`TelegramNetworkError` / `TelegramServerError`** — logs warning,
  sleeps `TELEGRAM_RETRY_DELAY` seconds, retries.

---

## Redis & FSM State

### Why Redis

`FSM_STORAGE=memory` loses state on every restart. Users mid-wizard
("Choose input method → Photo → [crash] → ???") get dumped to the home
screen with no error. Redis persists that state.

### Setup

```env
FSM_STORAGE=redis
REDIS_URL=redis://redis:6379/0
```

Keys are prefixed `cashback_fsm:`. You can share a Redis instance with
other apps as long as no one else uses that prefix.

### Memory usage

Aiogram's Redis state storage stores:

- Per-user FSM state: ~few hundred bytes.
- Per-user FSM data: `WorkflowState` serialised as JSON, typically < 2 KB.

For N active users (where "active" = started a wizard in the last 14
days), expect N × ~3 KB. 100 K active users → ~300 MB.

### Monitoring

```bash
redis-cli -u $REDIS_URL INFO memory
redis-cli -u $REDIS_URL DBSIZE
redis-cli -u $REDIS_URL --scan --pattern 'cashback_fsm:*' | wc -l
```

### Graceful degradation

If `FSM_STORAGE=redis` but `REDIS_URL` is empty, runtime logs a warning
and falls back to `MemoryStorage` (not a hard failure). If Redis goes down
mid-run, aiogram will raise on next access; the bot will log the error
and the user will see a generic error message — they can resume by
restarting the wizard.

---

## Health, Readiness & Liveness

### `GET /health`

```json
{
  "status": "ok",                              // or "degraded"
  "db": "ok",                                  // "ok" | "error" | "n/a"
  "telegram": "ok",                            // "ok" | "error" | "n/a"
  "ocr": {"primary": "auto", "status": "ok"},
  "version": "<git-sha-or-dev>"
}
```

- **DB probe**: `SELECT 1` with 2-second timeout.
- **Telegram probe**: `bot.get_me()` with 3-second timeout.
- **`n/a`**: probe not applicable (e.g. web-only deployment has no bot
  ping). Does **not** flag the response as degraded.

HTTP status: `200` when `ok`, `503` when `degraded`.

### Kubernetes probe example

```yaml
readinessProbe:
  httpGet: { path: /health, port: 8080 }
  initialDelaySeconds: 15
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
livenessProbe:
  httpGet: { path: /health, port: 8080 }
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 5
```

### Docker HEALTHCHECK

Already baked into the image:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1
```

---

## Prometheus Metrics

### Exposition

`GET /metrics` returns Prometheus text format.

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8080/metrics
```

When `METRICS_TOKEN` is empty, the endpoint is unauthenticated. **Do not
leave it open in production.**

### Metrics reference

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `cashback_bot_requests_total` | Counter | `handler`, `status` | Count of handler invocations. Labels: handler function name (`on_photo`, `on_start`, …), status `ok`/`error`. |
| `cashback_bot_request_duration_seconds` | Histogram | `handler` | Per-handler latency. Use `histogram_quantile()` for p50/p95/p99. |
| `cashback_bot_ocr_calls_total` | Counter | `provider`, `result` | OCR adapter call counts. Provider: `tesseract` / `openai`. Result: `ok` / `error` / `empty`. |
| `cashback_bot_active_users_total` | Gauge | — | Unique user ids seen since process start. Drops to 0 on restart — use `increase()` to see daily active counts. |

### Grafana panel ideas

- **Handler latency** — `histogram_quantile(0.95, rate(cashback_bot_request_duration_seconds_bucket[5m])) by (handler)`.
- **Error rate** — `sum(rate(cashback_bot_requests_total{status="error"}[5m])) / sum(rate(cashback_bot_requests_total[5m]))`.
- **OCR mix** — `sum(rate(cashback_bot_ocr_calls_total[1h])) by (provider)` — shows whether Tesseract is handling most load or OpenAI is being leaned on.
- **Active users** — `max_over_time(cashback_bot_active_users_total[24h])`.

### Alerting thresholds (suggestions)

| Rule | When to fire |
|---|---|
| `ErrorRate5xx` | `error_rate > 0.05` for 5 min |
| `HighLatency` | `p95 > 3s` on any handler for 5 min |
| `OCRFailures` | `rate(cashback_bot_ocr_calls_total{result="error"}[5m]) > 0.1` |
| `HealthDegraded` | `/health` 503 for 1 min |

---

## Structured Logging

### Format

Production (`LOG_LEVEL != DEBUG`): JSON lines.

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

Dev (`LOG_LEVEL=DEBUG`): colourful `ConsoleRenderer` output.

### Correlation id

- **Telegram**: set by `LoggingMiddleware` — 8-char uuid per update.
- **Web**: set by `_CorrelationIdMiddleware` — reads `X-Request-Id` if
  provided, otherwise generates. Echoed back in response headers.

All `structlog` calls within the same task pick up the id automatically.
stdlib `logging` calls don't (until the project fully migrates away from
`logging.getLogger()`), but the output is still routed through the
structlog formatter.

### Log aggregation

Recommended fields to index:

- `correlation_id` (primary key for a single trace)
- `user_id`
- `handler`
- `status`
- `level`

Grepping one user's session across adapters:

```
{"user_id":12345} | sort by timestamp
```

Grepping one request end-to-end:

```
{"correlation_id":"a1b2c3d4"}
```

---

## Database Backups & Migrations

### Backup strategy

`pg_dump` works for deployments up to a few GB. For larger:

```bash
# Nightly full dump
pg_dump --host=$POSTGRES_HOST --user=$POSTGRES_USER --format=custom \
        --file=/backups/cashback-$(date +%Y%m%d).pgdump cashback_bot
```

Retain at least 7 daily + 4 weekly + 12 monthly dumps. Verify restores
monthly against a staging database.

### Migrations at boot

`AUTO_MIGRATE=true` calls `alembic upgrade head` on startup, retrying up
to `MIGRATION_MAX_ATTEMPTS` × `MIGRATION_RETRY_DELAY` seconds. Useful for:

- Personal / small deployments where schema drift is rare.
- Kubernetes rollouts where all pods land on the same revision.

### Migrations as a separate step

For larger ops teams, set `AUTO_MIGRATE=false` and run:

```bash
alembic upgrade head
```

as a pre-deploy Job (Kubernetes) or an init step in CI/CD. Roll the
application image only after the job succeeds.

### Rollback

```bash
alembic downgrade -1       # one revision back
alembic downgrade <rev>    # to a specific revision
alembic current            # what's currently applied
```

The identity migration (0002) has a meaningful downgrade path — it
preserves the telegram_user_id back into `users`. The performance-indexes
migration (0003) is purely additive, so downgrade just drops the indexes.

### Current migration chain

1. `20260306_0001_initial.py` — base schema.
2. `20260311_0002_platform_identity.py` — split telegram → `user_identities`.
3. `20260424_0003_performance_indexes.py` — covering indexes for ranking
   JOIN and reminder dedup.

---

## OCR Provider Setup

### Tesseract only

```env
OCR_PROVIDER=tesseract
TESSERACT_PATH=tesseract      # or absolute path on Windows
OCR_TIMEOUT=20
```

No outbound network calls, no AI billing. Works well on clean
white-background screenshots; struggles with dark mode and anti-aliased
bank UIs.

### OpenAI Vision (or compatible)

```env
OCR_PROVIDER=openai
OPENAI_API_KEY=<your key>
OPENAI_MODEL=gpt-4o           # or any vision-capable model
OPENAI_BASE_URL=              # empty = real OpenAI
OPENAI_VISION_TIMEOUT=60
OPENAI_VISION_MAX_TOKENS=1024
```

### Compatible gateways

| Gateway | `OPENAI_BASE_URL` | Notes |
|---|---|---|
| Real OpenAI | (empty) | Direct — best quality, hardest to access from RU. |
| ProxyAPI | `https://api.proxyapi.ru/openai/v1` | Russian proxy, credit-card payment. |
| VSEgpt | `https://api.vsegpt.ru/v1` | Similar. |
| Ollama (self-hosted) | `http://localhost:11434/v1` | Needs a vision-capable local model (e.g. `llava:13b`). |
| LM Studio | `http://localhost:1234/v1` | Similar. |
| Together.ai | `https://api.together.xyz/v1` | Cheaper vision. |

All handle the same chat-completions-with-image payload; only the URL
changes.

### Composite (local-first, recommended)

```env
OCR_PROVIDER=auto
OPENAI_API_KEY=<your key>     # required for the AI fallback to actually fire
```

Tesseract runs first. If it returns empty or times out, OpenAI is called
as a fallback. `errors.broken_image` and `errors.file_too_large` are not
escalated — both engines would fail equally.

Cost model: on clean screenshots Tesseract handles ~70–90% of uploads for
free. The AI bill is only paid on the hard cases.

### Monitoring OCR

```promql
# OCR success rate by provider
sum(rate(cashback_bot_ocr_calls_total{result="ok"}[5m])) by (provider)
  /
sum(rate(cashback_bot_ocr_calls_total[5m])) by (provider)

# Fallback rate (how often AI kicks in)
sum(rate(cashback_bot_ocr_calls_total{provider="openai"}[5m]))
  /
sum(rate(cashback_bot_ocr_calls_total{provider="tesseract"}[5m]))
```

---

## Security Posture

### Pre-flight check (Settings validator)

`Settings` refuses to construct when `APP_ENABLE_WEB=true` and
`WEB_SESSION_SECRET` is the default placeholder. You'll see a
`ValueError` on startup — that's the intended behaviour. Fix the env and
retry.

### TLS

- HTTPS terminates at your reverse proxy (nginx / Caddy / Traefik / cloud
  ALB). The Python app speaks plain HTTP on port 8080.
- Set `WEB_SECURE_COOKIES=true` so session cookies are only sent over HTTPS.
- Uvicorn accepts `proxy_headers=True` — the app reads `X-Forwarded-*`
  correctly.

### Rate limits

| Where | Limit | Override |
|---|---|---|
| Telegram messages / callbacks per user | 30 / min (burst 30) | Hardcoded defaults in `TelegramDependencies` |
| Telegram photos per user | 5 burst, refill 1 / 10s | Hardcoded in `runtime.py` |
| Public `/api/*` per IP | `API_RATE_LIMIT_PER_MINUTE` (60) | Env var |

The web rate limiter is in-process. For multi-replica deployments, also
rate-limit at the edge (nginx `limit_req_zone`, CloudFront, Cloudflare).

### Secrets rotation

```bash
# Generate a new value
NEW_SECRET=$(openssl rand -hex 32)

# Update the runtime env
# (write to Vault / AWS Secrets Manager / k8s Secret / your store of choice)

# Roll the deployment
kubectl rollout restart deployment/cashback-web
```

For `WEBHOOK_SECRET` specifically, you must also call Telegram to update
the stored secret:

```bash
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://your-domain.com/bot/webhook" \
  -d "secret_token=${NEW_SECRET}" \
  -d "drop_pending_updates=false"
```

Then restart the bot service so `runtime._run_webhook_adapter` picks up
the new env — the value it sends in `set_webhook` must match what the web
app compares against.

### Dependency audit

```bash
pip install pip-audit
pip-audit --requirement requirements.txt
```

Not yet wired into CI — candidate for a future task.

---

## Upgrade Procedure

### Minor release (bug fix, no schema change)

1. Deploy new image to staging.
2. Smoke-test `/health` + `/metrics`.
3. Manually exercise a happy path (add bank, `/best`, upload photo).
4. Tag the current production image as `cashback:previous`.
5. Roll production to the new image.
6. Watch error rate and latency for 10 min.
7. If anything looks wrong, roll back to `cashback:previous`.

### Major release (new schema, env vars)

1. Review the new migration file — does it have a sane downgrade?
2. Update the env template (`.env.example`) — are new variables
   documented?
3. Update the Prometheus alert thresholds if labels change.
4. Deploy to staging with `AUTO_MIGRATE=true`, verify.
5. Production: run the migration as a separate step (via a Job or a
   one-shot container) **before** rolling the app.
6. Roll the app.
7. Keep an eye on `/metrics` for regressed latency on the changed
   queries.

### Rolling back a migration

```bash
alembic downgrade -1
```

Then roll the app to the previous image tag. If the migration was
destructive (dropped a column), you need a restore from backup.

---

## Incident Runbook

### Symptom: users can't send /start

**Check** `/health` → `telegram`. If `error`:

1. `curl "https://api.telegram.org/bot${BOT_TOKEN}/getMe"` — if 401, bad
   token. If timeout, DNS or firewall.
2. In webhook mode, `getWebhookInfo` → `last_error_message` often
   diagnoses it.
3. In polling mode, look for `TelegramUnauthorizedError` /
   `TelegramNetworkError` in logs.

### Symptom: OCR always fails

1. `/metrics` → `cashback_bot_ocr_calls_total{result="error"}` rate
   increasing?
2. Log search: `event="OCR error"` → typically reveals the root cause
   (rate-limit from OpenAI, missing key, Tesseract binary not found).
3. Swap `OCR_PROVIDER=tesseract` temporarily to isolate.
4. If OpenAI: check key quota and billing. If Tesseract: verify
   `TESSERACT_PATH` and language pack.

### Symptom: users lose wizard state

`FSM_STORAGE=memory` + a restart. Switch to Redis. If already on Redis:

1. `redis-cli ping` from the bot container — is Redis reachable?
2. `redis-cli INFO memory` — is Redis OOM-killed? Raise the limit or add
   a TTL cleanup.

### Symptom: /health returns 503

1. Response body tells you which probe failed.
2. `db: error` → check Postgres liveness, connection pool, credentials.
3. `telegram: error` → see "users can't send /start" above.

### Symptom: latency spike on /best

1. `/metrics` → `histogram_quantile(0.95, ...)` for `on_best_command`
   rising?
2. Ranking cache might be cold. If traffic recently shifted (many new
   users / a spike in `invalidate()` calls), expect a transient spike
   as the cache warms up.
3. Check Postgres slow queries — `pg_stat_statements` on a query over
   `banks` or `cashback_items`.
4. If slow queries hit the bulk ranking JOIN, verify the migration
   `20260424_0003` has been applied (`ix_cashback_items_bank_category`
   index exists).

### Symptom: webhook returns 403 repeatedly

1. `getWebhookInfo` shows `last_error_message: ...`.
2. Verify `WEBHOOK_SECRET` in env matches what was passed to
   `setWebhook`. If they diverged, re-run `setWebhook` with the current
   env value.
3. If the secret is right, check that the reverse proxy isn't stripping
   the `X-Telegram-Bot-Api-Secret-Token` header (nginx `proxy_pass_header`).

### Symptom: reminder not delivered

1. Log search: `event="reminder dispatched", user_id=<N>` — was it
   attempted?
2. If not attempted: `event="reminder skipped"` (already sent this month),
   or `user.notifications_enabled=false`.
3. If attempted and failed: look for `event="Reminder delivery failed"` —
   bot's `send_message` probably got a 403 (user blocked the bot) or 400
   (invalid chat_id).

---

## Capacity Planning

### Sizing rules of thumb (single web + bot combined)

| Active users | CPU | RAM | Notes |
|---|---|---|---|
| < 1 K | 0.5 core | 512 MB | Tesseract dominates CPU during OCR bursts |
| 1 K – 10 K | 1 core | 1 GB | Watch Redis memory |
| 10 K – 100 K | 2 cores, consider splitting web/bot | 2 GB | Scale web replicas; keep one polling bot |
| > 100 K | Webhook mode mandatory; N web replicas | 2+ GB per replica | Redis & Postgres become the capacity bottleneck |

### DB pool sizing

`DB_POOL_SIZE` × `replicas` should stay well below Postgres's
`max_connections` (default 100). For N replicas at pool size 10, leave
at least `100 - N*10` connections for admin / migration / monitoring.

### Telegram rate limits (Bot API)

- 30 messages per second globally per bot.
- ~20 messages per minute to the same chat.

Exceeding triggers 429. `TelegramReminderSender` paces reminders by
user id ordering — for huge user bases the reminder loop becomes the
long-running task.

### OpenAI cost model

Per-image cost depends on model + token usage. For GPT-4o at the time of
this writing: ~0.5¢ per image analysis. At 10 K uploads/month with 20%
AI fallback rate, that's ~$10/month.

---

## Appendix: Example nginx reverse proxy

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Allow the Telegram webhook to pass through with its secret header.
    location /bot/webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        # Don't strip the secret header.
        proxy_pass_request_headers on;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        # Request-id for end-to-end tracing. The web middleware will
        # respect an incoming X-Request-Id if present.
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
