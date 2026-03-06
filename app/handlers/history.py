from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.history import history_keyboard
from app.utils.callback import nav

router = Router(name="history")


@router.message(Command("history"))
@router.callback_query(F.data == nav("history"))
async def history_screen(
    event: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    entries = await app_container.catalog_service.list_history(session, db_user)
    if not entries:
        text = app_container.localizer.gettext(db_user.language, "messages.empty_history")
    else:
        lines = [
            app_container.localizer.gettext(
                db_user.language,
                "labels.history_entry",
                created_at=entry.created_at.isoformat(sep=" ", timespec="minutes"),
                action=entry.action,
            )
            for entry in entries
        ]
        text = app_container.localizer.gettext(db_user.language, "screens.history", entries="\n".join(lines))
    await screen_renderer.show_screen(
        event,
        state,
        text,
        reply_markup=history_keyboard(app_container.localizer, db_user.language),
    )
