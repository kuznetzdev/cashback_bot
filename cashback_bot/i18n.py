from __future__ import annotations

"""Simple translation helper supporting RU/EN locales."""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Translator:
    default_locale: str = "ru"
    _translations: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self._translations:
            return
        self._translations = {
            "en": {
                "start_message": "Welcome to Cashback Assistant! Upload tariff screenshots or type categories.",
                "main_menu_title": "Main menu",
                "btn_add_bank": "Add bank",
                "btn_import_photo": "Import more photos",
                "btn_show_global_rating": "Show my global rating",
                "btn_settings": "Settings",
                "btn_edit_categories": "Edit categories",
                "btn_back": "Back",
                "ocr_in_progress": "Running OCR…",
                "ocr_failed": "OCR failed, please try again or use manual input.",
                "parse_failed": "Could not parse categories.",
                "categories_preview": "Preview categories before saving.",
                "category_menu_header": "Category actions",
                "ranking_header": "Top banks for you:",
                "queue_busy": "Still processing your previous photo. Please wait.",
                "saved": "Saved.",
            },
            "ru": {
                "start_message": "Добро пожаловать в Cashback Assistant! Загрузите скрин тарифов или введите категории.",
                "main_menu_title": "Главное меню",
                "btn_add_bank": "Добавить банк",
                "btn_import_photo": "Импортировать ещё фото",
                "btn_show_global_rating": "Показать мой глобальный рейтинг",
                "btn_settings": "Настройки",
                "btn_edit_categories": "Редактировать категории",
                "btn_back": "Назад",
                "ocr_in_progress": "Запускаю OCR…",
                "ocr_failed": "Не получилось распознать. Попробуйте ещё раз или вручную.",
                "parse_failed": "Не удалось разобрать категории.",
                "categories_preview": "Просмотрите категории перед сохранением.",
                "category_menu_header": "Действия с категорией",
                "ranking_header": "Лучшие банки для вас:",
                "queue_busy": "Предыдущее фото ещё обрабатывается. Подождите.",
                "saved": "Сохранено.",
            },
        }

    def translate(self, key: str, locale: str | None = None) -> str:
        catalog = self._translations.get(locale or self.default_locale) or self._translations[self.default_locale]
        return catalog.get(key, key)
