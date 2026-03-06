from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.settings import settings_keyboard
from app.utils.callback import split_nav, nav

router = Router(name="settings")


async def _show_settings(
    event: Message | CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    language_label_key = "labels.language_en" if db_user.language == "en" else "labels.language_ru"
    notifications_key = "labels.notifications_on" if db_user.notifications_enabled else "labels.notifications_off"
    await screen_renderer.show_screen(
        event,
        state,
        app_container.localizer.gettext(
            db_user.language,
            "screens.settings",
            language=app_container.localizer.gettext(db_user.language, language_label_key),
            notifications=app_container.localizer.gettext(db_user.language, notifications_key),
        ),
        reply_markup=settings_keyboard(app_container.localizer, db_user.language, db_user.notifications_enabled),
    )


@router.message(Command("settings"))
@router.callback_query(F.data == nav("settings"))
async def settings_screen(
    event: Message | CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await _show_settings(event, state, db_user, app_container, screen_renderer)


@router.callback_query(F.data.startswith(f"{nav('set_lang')}:"))
async def set_language(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    parts = split_nav(callback.data or "")
    if len(parts) != 2:
        return
    await app_container.catalog_service.update_language(session, db_user, parts[1])
    await _show_settings(callback, state, db_user, app_container, screen_renderer)


@router.callback_query(F.data == nav("toggle_notifications"))
async def toggle_notifications(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await app_container.catalog_service.toggle_notifications(session, db_user)
    await _show_settings(callback, state, db_user, app_container, screen_renderer)
