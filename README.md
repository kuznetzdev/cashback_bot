# cashback_bot

Asynchronous Telegram bot that helps users capture purchase receipts, extract cashback
information via OCR/NLP, and review analytics in a personal cabinet.

## Local development

1. Create a Python virtual environment (3.11+) and install dependencies:

   ```bash
   pip install -r project/requirements.txt
   ```

2. Export the Telegram bot token and optional overrides:

   ```bash
   export BOT_TOKEN="<your_token>"
   export DB_PATH="./data/cashback.sqlite3"  # optional
   ```

3. Run the bot:

   ```bash
   python -m project.bot
   ```

## Docker

```
docker build -t cashback-bot project/
docker run --rm -e BOT_TOKEN="<your_token>" cashback-bot
```

## Project structure

```
project/
├── bot.py                # Telegram bot entrypoint
├── config.py             # Environment-driven configuration
├── services/             # Async DB/OCR/NLP/analytics/scheduler layers
├── i18n/                 # Localization utilities (EN/RU)
├── requirements.txt
└── Dockerfile
```
