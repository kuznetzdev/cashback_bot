from __future__ import annotations

import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


class TelegramScreenRenderer:
    async def show_screen(
        self,
        event: Message | CallbackQuery,
        state: FSMContext,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message:
        data = await state.get_data()
        last_message_id = data.get("last_screen_message_id")

        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message and (last_message_id is None or event.message.message_id == last_message_id):
                try:
                    await event.message.edit_text(text=text, reply_markup=reply_markup)
                    await state.update_data(last_screen_message_id=event.message.message_id)
                    return event.message
                except TelegramBadRequest:
                    pass

        source_message = event.message if isinstance(event, CallbackQuery) else event
        if last_message_id and source_message.message_id != last_message_id:
            await self.delete_message_best_effort(source_message.bot, source_message.chat.id, last_message_id)

        new_message = await source_message.answer(text, reply_markup=reply_markup)
        await state.update_data(last_screen_message_id=new_message.message_id)
        return new_message

    async def send_status(self, message: Message, text: str) -> Message:
        return await message.answer(text)

    async def delete_message_best_effort(self, bot, chat_id: int, message_id: int) -> None:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramAPIError:
            logger.debug("Failed to delete message %s in chat %s", message_id, chat_id)

    async def notify_error(self, event: Message | CallbackQuery, text: str) -> None:
        if isinstance(event, CallbackQuery):
            try:
                await event.answer(text, show_alert=True)
            except TelegramAPIError:
                if event.message:
                    await event.message.answer(text)
            return
        await event.answer(text)
