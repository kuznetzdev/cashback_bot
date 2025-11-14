"""Simple localisation store used by the cashback bot."""
from __future__ import annotations

from typing import Dict

from project.services.ui import STATUS_MESSAGES


DEFAULT_LOCALE = "ru"


_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        "main_menu.title": "Выберите раздел",
        "main_menu.add_bank": "Добавить банк",
        "main_menu.manual_templates": "Шаблоны чеков",
        "main_menu.pro_analytics": "PRO-аналитика",
        "main_menu.recommendations": "Рекомендации",
        "main_menu.history": "История",
        "main_menu.gamification": "Геймификация",
        "main_menu.notifications": "Уведомления",
        "wizard.bank.title": "Мастер добавления банка",
        "wizard.bank.step.name": "Введите название банка",
        "wizard.bank.step.account": "Добавьте счёт или карту",
        "wizard.bank.step.preferences": "Уточните предпочтения кешбэка",
        "wizard.bank.completed": "Банк добавлен!",
        "templates.title": "Шаблоны чеков",
        "templates.add": "Добавить шаблон",
        "analytics.title": "PRO-аналитика",
        "analytics.processed": "Собираем аналитику",
        "recommendations.title": "Рекомендации",
        "history.title": "История операций",
        "gamification.title": "Геймификация",
        "notifications.title": "Настройки уведомлений",
        "notifications.mode.smart": "Умные уведомления",
        "notifications.mode.weekly": "Еженедельный дайджест",
        "notifications.mode.off": "Выключить уведомления",
        "status.processing": STATUS_MESSAGES["processing"],
        "status.ready": STATUS_MESSAGES["ready"],
        "status.error": STATUS_MESSAGES["error"],
        "status.cancelled": STATUS_MESSAGES["cancelled"],
        "empty.history": "История пуста. Добавьте операции, чтобы увидеть аналитику.",
        "analytics.summary": "За месяц кешбэк: {amount} ₽",
        "templates.manual_prompt": "Опишите шаблон вручную",
        "extensions.gamification.level": "Ваш уровень: {level}",
        "extensions.recommendation.best_offer": "Лучшее предложение: {offer}",
    }
}


def translate(key: str, locale: str = DEFAULT_LOCALE, **kwargs: object) -> str:
    """Fetch a translation string with optional formatting."""

    template = _TRANSLATIONS.get(locale, {}).get(key, key)
    if kwargs:
        return template.format(**kwargs)
    return template


__all__ = ["translate", "DEFAULT_LOCALE"]
