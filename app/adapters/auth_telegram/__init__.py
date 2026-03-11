"""Telegram identity adapter."""

from app.adapters.auth_telegram.verifier import verify_telegram_login

__all__ = ["verify_telegram_login"]
