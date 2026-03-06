from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.db.models import User
from app.handlers.helpers import show_home_screen
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.home import home_keyboard
from app.utils.callback import nav

router = Router(name="home")


@router.callback_query(F.data == nav("home"))
async def home_callback(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await show_home_screen(callback, state, db_user, app_container, screen_renderer)


@router.callback_query(F.data == nav("help"))
async def help_callback(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.help"),
        reply_markup=home_keyboard(app_container.localizer, db_user.language),
    )
