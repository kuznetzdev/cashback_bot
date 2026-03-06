from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer

router = Router(name="common")


@router.message(StateFilter(None), F.text)
async def common_text_handler(
    message: Message,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    text = message.text or ""
    best_query = app_container.parser_service.understand_best_query(text)
    if best_query:
        entries = await app_container.catalog_service.list_ranking_entries(session, db_user)
        leader = app_container.ranking_service.best_for_query(entries, best_query.normalized_category, db_user.language)
        if leader is None:
            await screen_renderer.notify_error(
                message,
                app_container.localizer.gettext(db_user.language, "messages.no_ranking_data"),
            )
            return
        await message.answer(
            app_container.localizer.gettext(
                db_user.language,
                "messages.best_answer",
                category=leader.category_name,
                percent=leader.best_percent,
                banks=", ".join(leader.bank_names),
            )
        )
        return

    delete_intent = app_container.parser_service.understand_delete_command(text)
    if delete_intent:
        if delete_intent.kind == "bank":
            bank = await app_container.catalog_service.delete_bank_by_name(session, db_user, delete_intent.target)
            await message.answer(
                app_container.localizer.gettext(db_user.language, "messages.deleted_bank") + f" ({bank.bank_name})"
            )
            return
        deleted_count, affected_banks = await app_container.catalog_service.delete_category_by_query(
            session,
            db_user,
            delete_intent.target,
        )
        await message.answer(
            app_container.localizer.gettext(
                db_user.language,
                "messages.deleted_category",
                count=deleted_count,
                banks=affected_banks,
            )
        )
        return

    await screen_renderer.notify_error(
        message,
        app_container.localizer.gettext(db_user.language, "errors.unknown_command"),
    )
