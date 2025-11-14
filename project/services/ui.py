"""Unified UI helpers for rendering disappearing inline keyboards."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Sequence

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ButtonSpec:
    """Descriptor for a single inline button."""

    text: str
    callback_data: str


KeyboardLayout = Sequence[Sequence[ButtonSpec | tuple[str, str]]]


def build_keyboard(layout: KeyboardLayout | None) -> InlineKeyboardMarkup | None:
    if not layout:
        return None
    normalized: list[list[InlineKeyboardButton]] = []
    for row in layout:
        buttons: list[InlineKeyboardButton] = []
        for button in row:
            if isinstance(button, ButtonSpec):
                buttons.append(
                    InlineKeyboardButton(button.text, callback_data=button.callback_data)
                )
            else:
                text, callback_data = button
                buttons.append(InlineKeyboardButton(text, callback_data=callback_data))
        normalized.append(buttons)
    return InlineKeyboardMarkup(normalized)


async def render_screen(
    update: Update | CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    keyboard: KeyboardLayout | None = None,
    status: str | None = None,
    parse_mode: str = ParseMode.HTML,
    show_typing: bool = False,
) -> Message:
    """Render a screen ensuring previous keyboards disappear."""

    if isinstance(update, CallbackQuery):
        query = update
        chat_id = query.message.chat_id if query.message else None
    else:
        chat = update.effective_chat
        chat_id = chat.id if chat else None

    if chat_id is None:
        raise RuntimeError("Cannot resolve chat for rendering")

    if show_typing:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to send typing indicator")

    markup = build_keyboard(keyboard)
    message_id = context.user_data.get("screen_message_id")
    status_id = context.user_data.get("status_message_id")

    async def _cleanup_status() -> None:
        if not status_id:
            return
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_id)
        except BadRequest:
            LOGGER.debug("Status message %s already gone", status_id)
        except Exception:  # pragma: no cover - log unexpected
            LOGGER.exception("Failed to delete status message %s", status_id)
        finally:
            context.user_data.pop("status_message_id", None)

    await _cleanup_status()

    if status:
        status_message = await context.bot.send_message(
            chat_id=chat_id,
            text=status,
            parse_mode=parse_mode,
        )
        context.user_data["status_message_id"] = status_message.message_id

    if isinstance(update, CallbackQuery) and update.message:
        query_message = update.message
        current_id = query_message.message_id
        if message_id == current_id:
            try:
                await query_message.edit_text(text, reply_markup=markup, parse_mode=parse_mode)
                return query_message
            except BadRequest:
                LOGGER.debug("Failed to edit message %s, fallback to new", current_id)
        else:
            try:
                await query_message.delete()
            except BadRequest:
                LOGGER.debug("Message %s already deleted", query_message.message_id)
            except Exception:
                LOGGER.exception("Failed to delete previous message")

        new_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
            parse_mode=parse_mode,
        )
        context.user_data["screen_message_id"] = new_message.message_id
        return new_message

    if isinstance(update, Update):
        incoming_message = update.effective_message
        if incoming_message and message_id and incoming_message.message_id != message_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except BadRequest:
                LOGGER.debug("Previous screen message already gone")
            except Exception:
                LOGGER.exception("Failed to delete previous screen message")

        new_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
            parse_mode=parse_mode,
        )
        context.user_data["screen_message_id"] = new_message.message_id
        return new_message

    raise RuntimeError("Unsupported update type for rendering")


async def notify_processing(
    update: Update | CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    message: str,
) -> None:
    """Show a transient processing notification."""

    chat = update.effective_chat if isinstance(update, Update) else update.message.chat
    if chat is None:
        raise RuntimeError("Cannot resolve chat for processing notification")
    status_message = await context.bot.send_message(chat_id=chat.id, text=message)
    context.user_data["status_message_id"] = status_message.message_id

    async def _auto_cleanup() -> None:
        await asyncio.sleep(3)
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=status_message.message_id)
        except BadRequest:
            LOGGER.debug("Processing message already deleted")
        except Exception:
            LOGGER.exception("Failed to clean processing message")
        finally:
            context.user_data.pop("status_message_id", None)

    asyncio.create_task(_auto_cleanup())

