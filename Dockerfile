FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
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
RUN mkdir -p /app/tmp /app/temp \
    && chown -R cashback:cashback /app

USER cashback

CMD ["python", "-m", "app.main"]
