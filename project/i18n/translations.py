"""Localization helpers for the cashback bot."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class Translator:
    default_locale: str = "en"

    _translations: Dict[str, Dict[str, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._translations = {
            "en": {
                "start_message": "Welcome to Cashback Assistant! Choose an option below.",
                "main_menu": "Main menu",
                "menu_manual": "Manual input",
                "menu_analytics": "Analytics",
                "menu_cabinet": "Personal cabinet",
                "menu_settings": "Settings",
                "recent_receipts": "Recent receipts:",
                "receipt_added": "Receipt saved successfully.",
                "receipt_deleted": "Last receipt deleted.",
                "no_receipt": "No receipts found.",
                "send_receipt_prompt": "Send a receipt photo or enter details manually.",
                "manual_input_prompt": "Please send details in the format: merchant; category; amount; cashback; currency; YYYY-MM-DD",
                "analytics_header": "Your top cashback categories:",
                "analytics_row": "{idx}. {category} — {cashback:.2f} cashback ({rate:.2%})",
                "reminder": "Don't forget to upload receipts this month!",
                "unknown": "I didn't understand that. Use the menu to navigate.",
                "photo_prompt": "Use the menu to start receipt upload.",
                "ocr_failed": "OCR failed. Try manual input.",
                "parse_failed": "Could not parse receipt. Please send details manually.",
                "manual_format_error": "Format invalid. Please try again.",
                "manual_amount_error": "Amount or cashback is invalid. Please try again.",
                "best_cashback": "Best cashback category: {category} with {rate:.2%} return.",
                "no_cashback": "No cashback data yet.",
            },
            "ru": {
                "start_message": "Добро пожаловать в Cashback Assistant! Выберите действие ниже.",
                "main_menu": "Главное меню",
                "menu_manual": "Ввести вручную",
                "menu_analytics": "Аналитика",
                "menu_cabinet": "Личный кабинет",
                "menu_settings": "Настройки",
                "recent_receipts": "Последние чеки:",
                "receipt_added": "Чек успешно сохранён.",
                "receipt_deleted": "Последний чек удалён.",
                "no_receipt": "Чеки не найдены.",
                "send_receipt_prompt": "Отправьте фото чека или введите данные вручную.",
                "manual_input_prompt": "Отправьте данные в формате: магазин; категория; сумма; кешбэк; валюта; ГГГГ-ММ-ДД",
                "analytics_header": "Ваши лучшие категории кешбэка:",
                "analytics_row": "{idx}. {category} — {cashback:.2f} кешбэк ({rate:.2%})",
                "reminder": "Не забудьте загрузить чеки в этом месяце!",
                "unknown": "Я не понял сообщение. Воспользуйтесь меню.",
                "photo_prompt": "Используйте меню, чтобы начать загрузку чека.",
                "ocr_failed": "Распознавание не удалось. Попробуйте ввести данные вручную.",
                "parse_failed": "Не удалось разобрать чек. Введите данные вручную.",
                "manual_format_error": "Неверный формат. Попробуйте снова.",
                "manual_amount_error": "Некорректная сумма или кешбэк. Попробуйте снова.",
                "best_cashback": "Лучшая категория кешбэка: {category} с доходностью {rate:.2%}.",
                "no_cashback": "Данных по кешбэку пока нет.",
            },
        }

    def translate(self, key: str, locale: str | None = None) -> str:
        catalog = self._translations.get(locale or self.default_locale) or self._translations[self.default_locale]
        return catalog.get(key, key)
