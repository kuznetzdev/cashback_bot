from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramServerError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.adapters.telegram.callbacks import encode_action
from app.adapters.telegram.state import load_last_screen_message_id, save_last_screen_message_id
from app.application.workflow.models import Screen
from app.i18n.localizer import Localizer

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class TelegramScreenRenderer:
    def __init__(self, localizer: Localizer) -> None:
        self.localizer = localizer

    async def render(self, *, event: Message | CallbackQuery, state: FSMContext, screen: Screen, language: str) -> None:
        bot, chat_id = self._extract_destination(event)
        text = self._render_screen_text(screen, language)
        keyboard = self._build_keyboard(screen, language)

        previous_screen_id = await load_last_screen_message_id(state)
        if isinstance(event, Message):
            new_message = await self._send_message(bot=bot, chat_id=chat_id, text=text, markup=keyboard)
            new_message_id = new_message.message_id
            if previous_screen_id is not None and previous_screen_id != new_message_id:
                await self._safe_delete_message(bot, chat_id, previous_screen_id)
        else:
            new_message_id = await self._upsert_screen_message(
                bot=bot,
                chat_id=chat_id,
                previous_message_id=previous_screen_id,
                text=text,
                markup=keyboard,
            )
        await save_last_screen_message_id(state, new_message_id)

        if isinstance(event, CallbackQuery):
            await self._safe_answer_callback(event)
            await self._safe_delete_callback_source(event, keep_message_id=new_message_id)

    async def notify_status(self, event: Message | CallbackQuery, text: str, *, delete_after: bool = False) -> Message:
        bot, chat_id = self._extract_destination(event)
        status = await self._send_message(bot=bot, chat_id=chat_id, text=text)
        if delete_after:
            asyncio.create_task(self._delete_with_delay(bot, chat_id, status.message_id))
        return status

    async def notify_error(self, event: Message | CallbackQuery, text: str) -> None:
        bot, chat_id = self._extract_destination(event)
        await self._send_message(bot=bot, chat_id=chat_id, text=text)

    def _render_screen_text(self, screen: Screen, language: str) -> str:
        title = self.localizer.t(screen.title_key, language)
        body = self.localizer.t(screen.body_key, language, screen.body_params)
        if screen.title_key == screen.body_key:
            return body
        return f"{title}\n\n{body}"

    def _build_keyboard(self, screen: Screen, language: str) -> InlineKeyboardMarkup | None:
        if not screen.actions:
            return None
        rows: list[list[InlineKeyboardButton]] = []
        for action in screen.actions:
            label = self.localizer.t(action.label_key, language)
            callback_data = encode_action(action)
            rows.append([InlineKeyboardButton(text=label, callback_data=callback_data)])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _upsert_screen_message(
        self,
        *,
        bot: Bot,
        chat_id: int,
        previous_message_id: int | None,
        text: str,
        markup: InlineKeyboardMarkup | None,
    ) -> int:
        if previous_message_id is not None:
            try:
                await self._edit_message_text(
                    bot=bot,
                    chat_id=chat_id,
                    message_id=previous_message_id,
                    text=text,
                    markup=markup,
                )
                return previous_message_id
            except TelegramBadRequest as error:
                logger.debug("Failed to edit previous screen message %s: %s", previous_message_id, error)
                await self._safe_delete_message(bot, chat_id, previous_message_id)
        message = await self._send_message(bot=bot, chat_id=chat_id, text=text, markup=markup)
        return message.message_id

    @staticmethod
    async def _safe_answer_callback(callback: CallbackQuery) -> None:
        try:
            await callback.answer()
        except TelegramBadRequest:
            return

    async def _safe_delete_callback_source(self, callback: CallbackQuery, *, keep_message_id: int) -> None:
        message = callback.message
        if message is None:
            return
        if message.message_id == keep_message_id:
            return
        await self._safe_delete_message(callback.bot, message.chat.id, message.message_id)

    @staticmethod
    async def _safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> None:
        try:
            await _retryable_call(bot.delete_message, chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest:
            return

    @staticmethod
    async def _delete_with_delay(bot: Bot, chat_id: int, message_id: int, delay_seconds: float = 2.0) -> None:
        await asyncio.sleep(delay_seconds)
        await TelegramScreenRenderer._safe_delete_message(bot, chat_id, message_id)

    @staticmethod
    def _extract_destination(event: Message | CallbackQuery) -> tuple[Bot, int]:
        if isinstance(event, Message):
            return event.bot, event.chat.id
        if event.message is None:
            raise RuntimeError("CallbackQuery message is missing")
        return event.bot, event.message.chat.id

    async def _send_message(
        self,
        *,
        bot: Bot,
        chat_id: int,
        text: str,
        markup: InlineKeyboardMarkup | None = None,
    ) -> Message:
        return await _retryable_call(bot.send_message, chat_id=chat_id, text=text, reply_markup=markup)

    async def _edit_message_text(
        self,
        *,
        bot: Bot,
        chat_id: int,
        message_id: int,
        text: str,
        markup: InlineKeyboardMarkup | None,
    ) -> Message | bool:
        return await _retryable_call(
            bot.edit_message_text,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup,
        )


async def _retryable_call(func: Callable[P, Awaitable[R]], /, *args: P.args, **kwargs: P.kwargs) -> R:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
        retry=retry_if_exception_type((TelegramNetworkError, TelegramServerError, TimeoutError)),
        reraise=True,
    ):
        with attempt:
            return await func(*args, **kwargs)
    raise RuntimeError("Retrying loop ended without returning")
