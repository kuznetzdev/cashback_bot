"""Simple translation dictionary for Russian locale."""
from __future__ import annotations

from typing import Dict

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        "menu.main": "📊 Главное меню",
        "menu.analytics": "📈 PRO-аналитика",
        "menu.recommendations": "💡 Рекомендации",
        "menu.history": "🕑 История",
        "menu.gamification": "🏆 Геймификация",
        "menu.notifications": "🔔 Уведомления",
        "menu.templates": "🧩 Шаблоны",
        "menu.bank_wizard": "🏦 Добавить банк",
        "status.processing": "⏳ Обрабатываю…",
        "status.success": "✅ Готово",
        "status.error": "⚠️ Ошибка",
        "wizard.bank.step_name": "Введите название банка",
        "wizard.bank.step_product": "Выберите тип продукта",
        "wizard.bank.step_confirm": "Подтвердите добавление",
        "notifications.settings": "Выберите режим уведомлений",
        "templates.empty": "Шаблонов пока нет. Добавьте первый!",
        "history.empty": "История пуста",
        "analytics.empty": "Недостаточно данных для аналитики",
        "gamification.level": "Ваш уровень: {level}",
        "recommendations.title": "Персональные рекомендации",
    }
}


def translate(key: str, locale: str = "ru", **kwargs: str) -> str:
    value = TRANSLATIONS.get(locale, {}).get(key, key)
    if kwargs:
        try:
            return value.format(**kwargs)
        except KeyError:
            return value
    return value
