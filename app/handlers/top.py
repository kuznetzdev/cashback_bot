from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.home import home_keyboard
from app.keyboards.top import top_keyboard
from app.utils.callback import split_nav, nav

router = Router(name="top")


@router.message(Command("top"))
@router.callback_query(F.data == nav("top"))
async def top_screen(
    event: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    entries = await app_container.catalog_service.list_ranking_entries(session, db_user)
    if not entries:
        await screen_renderer.show_screen(
            event,
            state,
            app_container.localizer.gettext(db_user.language, "messages.no_ranking_data"),
            reply_markup=home_keyboard(app_container.localizer, db_user.language),
        )
        return

    leaders = app_container.ranking_service.top_by_category(entries, db_user.language)
    global_rating = app_container.ranking_service.top_global(entries)
    leader_lines = "\n".join(
        f"• {leader.category_name}: {leader.best_percent}% — {', '.join(leader.bank_names)}"
        for leader in leaders
    )
    global_lines = "\n".join(
        f"• {entry.bank_name}: {entry.score}"
        for entry in global_rating
    )
    text = app_container.localizer.gettext(
        db_user.language,
        "screens.top",
        leaders=leader_lines,
        global_rating=global_lines,
    )
    await screen_renderer.show_screen(
        event,
        state,
        text,
        reply_markup=top_keyboard(
            app_container.localizer,
            db_user.language,
            [leader.category_slug for leader in leaders],
            {leader.category_slug: leader.category_name for leader in leaders},
        ),
    )


@router.callback_query(F.data.startswith(f"{nav('top_category')}:"))
async def top_category(
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
    slug = parts[1]
    entries = await app_container.catalog_service.list_ranking_entries(session, db_user)
    leader = app_container.ranking_service.best_for_query(entries, slug, db_user.language)
    if leader is None:
        await screen_renderer.show_screen(
            callback,
            state,
            app_container.localizer.gettext(db_user.language, "messages.no_ranking_data"),
            reply_markup=home_keyboard(app_container.localizer, db_user.language),
        )
        return
    builder = InlineKeyboardBuilder()
    builder.button(text=app_container.localizer.gettext(db_user.language, "buttons.back"), callback_data=nav("top"))
    builder.button(text=app_container.localizer.gettext(db_user.language, "buttons.home"), callback_data=nav("home"))
    builder.adjust(1)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(
            db_user.language,
            "screens.top_category",
            category=leader.category_name,
            percent=leader.best_percent,
            banks=", ".join(leader.bank_names),
        ),
        reply_markup=builder.as_markup(),
    )
