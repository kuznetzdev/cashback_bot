"""User interface helpers for rendering structured Telegram screens."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

NAV_PREFIX = "nav:"
ACTION_PREFIX = "action:"
EDIT_PREFIX = "edit:"
DELETE_PREFIX = "del:"

DEFAULT_STYLE = {
    "parse_mode": "HTML",
}

STATUS_MESSAGES: Mapping[str, str] = {
    "processing": "⏳ Обрабатываю…",
    "ready": "✅ Готово",
    "error": "⚠️ Что-то пошло не так",
}

TYPING_INDICATORS: Mapping[str, str] = {
    "ocr": "🖨 Распознаю чек…",
    "nlp": "🧠 Анализирую покупки…",
    "db": "💾 Сохраняю результаты…",
}


@dataclass(frozen=True)
class Button:
    text: str
    callback_data: str


KeyboardLayout = List[List[Button]]


def render_screen(
    update: Optional[MutableMapping[str, object]],
    context: Optional[MutableMapping[str, object]],
    text: str,
    keyboard: KeyboardLayout,
) -> Dict[str, object]:
    """Return a structure describing the rendered screen."""
    message = {
        "text": text,
        "keyboard": [
            [
                {"text": button.text, "callback_data": button.callback_data}
                for button in row
            ]
            for row in keyboard
        ],
        "style": DEFAULT_STYLE,
    }
    if context is not None:
        context["last_screen"] = message
    if update is not None:
        update["rendered"] = message
    return message


def make_menu(button_rows: Sequence[Sequence[Button]]) -> KeyboardLayout:
    return [[button for button in row] for row in button_rows]


def make_back_button(target: str, text: str = "⬅️ Назад") -> Button:
    return Button(text=text, callback_data=f"{NAV_PREFIX}{target}")


def make_nav_button(target: str, text: str) -> Button:
    return Button(text=text, callback_data=f"{NAV_PREFIX}{target}")


def make_action_button(action: str, text: str) -> Button:
    return Button(text=text, callback_data=f"{ACTION_PREFIX}{action}")


def make_edit_button(entity: str, text: str) -> Button:
    return Button(text=text, callback_data=f"{EDIT_PREFIX}{entity}")


def make_delete_button(entity: str, text: str) -> Button:
    return Button(text=text, callback_data=f"{DELETE_PREFIX}{entity}")


def flatten_buttons(buttons: Iterable[Button]) -> List[Button]:
    return list(buttons)
