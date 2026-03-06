from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.history import HistoryService
from app.handlers.helpers import show_home_screen
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.home import home_keyboard

router = Router(name="start")


@router.message(Command("start"))
async def start_command(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await HistoryService(session).log(db_user.id, "user_started", {"telegram_user_id": db_user.telegram_user_id})
    await show_home_screen(message, state, db_user, app_container, screen_renderer)


@router.message(Command("help"))
async def help_command(
    message: Message,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await screen_renderer.show_screen(
        message,
        state,
        app_container.localizer.gettext(db_user.language, "screens.help"),
        reply_markup=home_keyboard(app_container.localizer, db_user.language),
    )
