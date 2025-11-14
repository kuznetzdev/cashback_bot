"""UI rendering utilities and keyboard builders for the cashback bot."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Mapping, MutableMapping, Optional

# Structured callback data prefixes recognised by the bot.
CALLBACK_NAV_PREFIX = "nav:"
CALLBACK_ACTION_PREFIX = "action:"
CALLBACK_EDIT_PREFIX = "edit:"
CALLBACK_DELETE_PREFIX = "del:"


@dataclass(frozen=True)
class KeyboardButton:
    """Represents a single inline button."""

    text: str
    callback_data: str


KeyboardLayout = List[List[KeyboardButton]]


def nav_callback(target: str) -> str:
    """Build a navigation callback payload."""

    return f"{CALLBACK_NAV_PREFIX}{target}"


def action_callback(action: str) -> str:
    """Build an action callback payload."""

    return f"{CALLBACK_ACTION_PREFIX}{action}"


def edit_callback(entity_id: str) -> str:
    """Build an edit callback payload."""

    return f"{CALLBACK_EDIT_PREFIX}{entity_id}"


def delete_callback(entity_id: str) -> str:
    """Build a delete callback payload."""

    return f"{CALLBACK_DELETE_PREFIX}{entity_id}"


def build_keyboard(rows: Iterable[Iterable[KeyboardButton]]) -> KeyboardLayout:
    """Normalise arbitrary iterables into a layout list."""

    return [list(row) for row in rows]


def single_column(buttons: Iterable[KeyboardButton]) -> KeyboardLayout:
    """Arrange buttons in a single column."""

    return [[button] for button in buttons]


def pairwise(buttons: Iterable[KeyboardButton]) -> KeyboardLayout:
    """Arrange buttons in rows of two."""

    layout: KeyboardLayout = []
    row: List[KeyboardButton] = []
    for button in buttons:
        row.append(button)
        if len(row) == 2:
            layout.append(row)
            row = []
    if row:
        layout.append(row)
    return layout


# Shared UI snippets for status indicators and reusable text fragments.
STATUS_MESSAGES = {
    "processing": "⏳ Обрабатываю…",
    "ready": "✅ Готово",
    "error": "⚠️ Произошла ошибка. Попробуйте ещё раз.",
    "cancelled": "✖️ Действие отменено.",
}

TYPING_INDICATOR = "typing"
UPLOADING_INDICATOR = "upload_document"


@dataclass
class RenderResult:
    """Structured output produced by :func:`render_screen`."""

    chat_id: Optional[int]
    text: str
    keyboard: Optional[KeyboardLayout]


class UIContextProtocol:
    """Simplified protocol for contexts used in tests and the bot."""

    ui_messages: List[RenderResult]


def render_screen(update: Mapping[str, object], context: MutableMapping[str, object], text: str,
                  keyboard: Optional[KeyboardLayout]) -> RenderResult:
    """Render a screen and keep track of it for assertions.

    In the real Telegram bot the function would send a message using the Bot API.
    Inside the tests we keep the render results inside the context so that
    we can assert on them without depending on Telegram specific classes.
    """

    chat_id = None
    if hasattr(update, "effective_chat") and getattr(update.effective_chat, "id", None) is not None:
        chat_id = update.effective_chat.id
    elif "chat_id" in update:
        chat_id = int(update["chat_id"])  # type: ignore[arg-type]

    layout = keyboard if keyboard else None
    result = RenderResult(chat_id=chat_id, text=text, keyboard=layout)
    message_log: List[RenderResult] = context.setdefault("ui_messages", [])  # type: ignore[assignment]
    message_log.append(result)
    return result
