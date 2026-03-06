from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.handlers.helpers import format_draft_items, show_home_screen
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.banks import (
    bank_details_keyboard,
    choose_bank_keyboard,
    confirm_delete_bank_keyboard,
    my_banks_keyboard,
)
from app.keyboards.home import home_keyboard
from app.keyboards.input_flow import input_method_keyboard
from app.schemas.cashback_item import DraftCashbackItem
from app.utils.callback import split_nav, nav
from app.utils.state import clear_flow_data, set_draft_items

router = Router(name="banks")


@router.message(Command("add"))
@router.callback_query(F.data == nav("add_bank"))
async def add_bank_entry(
    event: Message | CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await clear_flow_data(state)
    await screen_renderer.show_screen(
        event,
        state,
        app_container.localizer.gettext(db_user.language, "screens.choose_bank"),
        reply_markup=choose_bank_keyboard(app_container.localizer, db_user.language),
    )


@router.callback_query(F.data == nav("add_bank_other"))
async def add_other_bank(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    from app.utils.state import InputStates

    await state.set_state(InputStates.waiting_custom_bank_name)
    await state.update_data(flow_origin="create", selected_bank_id=None)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.enter_bank_name"),
    )


@router.callback_query(F.data.startswith(f"{nav('add_bank_select')}:"))
async def choose_popular_bank(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    parts = split_nav(callback.data or "")
    if len(parts) != 2:
        return
    index = int(parts[1])
    from app.core.constants import POPULAR_BANKS

    if index < 0 or index >= len(POPULAR_BANKS):
        return
    bank_name = POPULAR_BANKS[index]
    await state.update_data(
        flow_origin="create",
        selected_bank_id=None,
        selected_bank_name=bank_name,
    )
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.input_method", bank_name=bank_name),
        reply_markup=input_method_keyboard(app_container.localizer, db_user.language),
    )


@router.message(Command("my"))
@router.callback_query(F.data == nav("my_banks"))
async def my_banks(
    event: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    banks = await app_container.catalog_service.list_banks(session, db_user)
    if not banks:
        await screen_renderer.show_screen(
            event,
            state,
            app_container.localizer.gettext(db_user.language, "messages.empty_banks"),
            reply_markup=home_keyboard(app_container.localizer, db_user.language),
        )
        return
    await screen_renderer.show_screen(
        event,
        state,
        app_container.localizer.gettext(db_user.language, "screens.my_banks"),
        reply_markup=my_banks_keyboard(app_container.localizer, db_user.language, banks),
    )


@router.callback_query(F.data.startswith(f"{nav('bank')}:"))
async def bank_details(
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
    bank_id = int(parts[1])
    details = await app_container.catalog_service.get_bank_details(session, db_user, bank_id)
    items = [
        DraftCashbackItem(
            raw_category=item.raw_category,
            normalized_category=item.normalized_category,
            percent=item.percent,
            source_type=item.source_type,
        )
        for item in details.items
    ]
    text = app_container.localizer.gettext(
        db_user.language,
        "screens.bank_details",
        bank_name=details.bank_name,
        items=format_draft_items(app_container, db_user.language, items),
    )
    await screen_renderer.show_screen(
        callback,
        state,
        text,
        reply_markup=bank_details_keyboard(app_container.localizer, db_user.language, details.id),
    )


@router.callback_query(F.data.startswith(f"{nav('edit_bank')}:"))
async def edit_bank(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
) -> None:
    from app.handlers.preview import show_preview_screen

    parts = split_nav(callback.data or "")
    if len(parts) != 2:
        return
    bank_id = int(parts[1])
    details = await app_container.catalog_service.get_bank_details(session, db_user, bank_id)
    await set_draft_items(
        state,
        [
            DraftCashbackItem(
                raw_category=item.raw_category,
                normalized_category=item.normalized_category,
                percent=item.percent,
                source_type=item.source_type,
            )
            for item in details.items
        ],
    )
    await state.update_data(
        flow_origin="edit",
        selected_bank_id=details.id,
        selected_bank_name=details.bank_name,
        source_type=details.items[0].source_type if details.items else "manual",
    )
    await show_preview_screen(callback, state, db_user, app_container)


@router.callback_query(F.data.startswith(f"{nav('delete_bank')}:"))
async def confirm_delete_bank(
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
    bank_id = int(parts[1])
    details = await app_container.catalog_service.get_bank_details(session, db_user, bank_id)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.confirm_delete_bank", bank_name=details.bank_name),
        reply_markup=confirm_delete_bank_keyboard(app_container.localizer, db_user.language, bank_id),
    )


@router.callback_query(F.data.startswith(f"{nav('confirm_delete_bank')}:"))
async def delete_bank(
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
    bank_id = int(parts[1])
    await app_container.catalog_service.delete_bank(session, db_user, bank_id)
    await clear_flow_data(state)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "messages.deleted_bank"),
        reply_markup=home_keyboard(app_container.localizer, db_user.language),
    )
