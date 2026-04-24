FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        tesseract-ocr \
        tesseract-ocr-rus \
        libjpeg62-turbo-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 cashback \
    && useradd --system --uid 10001 --gid cashback --home-dir /app --shell /usr/sbin/nologin cashback

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure runtime-writable paths (OCR temp, alembic work) belong to the service user.
# The binary locations under /usr/bin are owned by root (read-only for cashback).
RUN mkdir -p /app/tmp /app/temp \
    && chown -R cashback:cashback /app /app/tmp /app/temp \
    && chmod 0755 /usr/bin/tesseract

USER cashback

# Exposed for orchestrators that probe the web adapter — non-web deployments
# can ignore this by setting APP_ENABLE_WEB=false (the probe will just fail
# but the container will still keep running since the bot loop is the main
# task). Pin to 8080 since that's the default WEB_PORT.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["python", "-m", "app.main"]
