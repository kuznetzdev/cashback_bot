from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.db.models import User
from app.handlers.helpers import format_draft_items, format_percent, show_home_screen, source_label
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.banks import bank_details_keyboard
from app.keyboards.preview import edit_item_keyboard, preview_keyboard
from app.schemas.cashback_item import DraftCashbackItem
from app.utils.callback import split_nav, nav
from app.utils.state import InputStates, clear_flow_data, get_draft_items, set_draft_items

router = Router(name="preview")


async def show_preview_screen(
    event: Message | CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer | None = None,
) -> None:
    screen_renderer = screen_renderer or TelegramScreenRenderer()
    data = await state.get_data()
    items = await get_draft_items(state)
    bank_name = data.get("selected_bank_name", "—")
    source_type = data.get("source_type", "manual")
    text = app_container.localizer.gettext(
        db_user.language,
        "screens.preview",
        bank_name=bank_name,
        items=format_draft_items(app_container, db_user.language, items),
        source_type=source_label(app_container.localizer, db_user.language, source_type),
    )
    if source_type == "template":
        text = f"{text}\n\n{app_container.localizer.gettext(db_user.language, 'messages.template_zero_hint')}"
    await screen_renderer.show_screen(
        event,
        state,
        text,
        reply_markup=preview_keyboard(app_container.localizer, db_user.language, items),
    )


@router.callback_query(F.data == nav("preview"))
async def preview_screen(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await show_preview_screen(callback, state, db_user, app_container, screen_renderer)


@router.callback_query(F.data.startswith(f"{nav('edit_item')}:"))
async def pick_item(
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
    items = await get_draft_items(state)
    if index < 0 or index >= len(items):
        return
    item = items[index]
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(
            db_user.language,
            "screens.choose_item_action",
            item=item.raw_category,
            percent=format_percent(item.percent),
        ),
        reply_markup=edit_item_keyboard(app_container.localizer, db_user.language, index),
    )


@router.callback_query(F.data == nav("add_item"))
async def add_item(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await state.update_data(pending_action="add_item", editing_index=None, pending_item_category=None)
    await state.set_state(InputStates.waiting_item_category)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.ask_item_category"),
    )


@router.callback_query(F.data.startswith(f"{nav('edit_item_category')}:"))
async def edit_item_category(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    parts = split_nav(callback.data or "")
    if len(parts) != 2:
        return
    await state.update_data(pending_action="edit_category", editing_index=int(parts[1]))
    await state.set_state(InputStates.waiting_item_category)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.ask_item_category"),
    )


@router.callback_query(F.data.startswith(f"{nav('edit_item_percent')}:"))
async def edit_item_percent(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    parts = split_nav(callback.data or "")
    if len(parts) != 2:
        return
    await state.update_data(pending_action="edit_percent", editing_index=int(parts[1]))
    await state.set_state(InputStates.waiting_item_percent)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.ask_item_percent"),
    )


@router.callback_query(F.data.startswith(f"{nav('delete_item')}:"))
async def delete_item(
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
    items = await get_draft_items(state)
    if index < 0 or index >= len(items):
        return
    items.pop(index)
    await set_draft_items(state, items)
    await show_preview_screen(callback, state, db_user, app_container, screen_renderer)


@router.message(InputStates.waiting_item_category, F.text)
async def receive_item_category(
    message: Message,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
) -> None:
    items = await get_draft_items(state)
    data = await state.get_data()
    category_name = (message.text or "").strip()
    if not category_name:
        raise ValidationError("errors.invalid_manual_input")
    normalized = app_container.category_service.normalize(category_name)
    pending_action = data.get("pending_action")
    if pending_action == "edit_category":
        index = data.get("editing_index")
        if index is None or index >= len(items):
            raise ValidationError("errors.invalid_manual_input")
        items[index] = items[index].model_copy(
            update={
                "raw_category": category_name,
                "normalized_category": normalized.slug,
            }
        )
        await set_draft_items(state, items)
        await state.update_data(pending_action=None, editing_index=None)
        await state.set_state(None)
        await show_preview_screen(message, state, db_user, app_container)
        return

        await state.update_data(
            pending_action="add_item_percent",
            pending_item_category=category_name,
            pending_item_normalized=normalized.slug,
        )
    await state.set_state(InputStates.waiting_item_percent)
    await message.answer(app_container.localizer.gettext(db_user.language, "screens.ask_item_percent"))


@router.message(InputStates.waiting_item_percent, F.text)
async def receive_item_percent(
    message: Message,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
) -> None:
    items = await get_draft_items(state)
    data = await state.get_data()
    try:
        percent = Decimal((message.text or "").strip().replace(",", "."))
    except InvalidOperation as error:
        raise ValidationError("errors.invalid_percent") from error
    if percent <= 0 or percent > 100:
        raise ValidationError("errors.invalid_percent")
    percent = percent.quantize(Decimal("0.01"))

    pending_action = data.get("pending_action")
    if pending_action == "edit_percent":
        index = data.get("editing_index")
        if index is None or index >= len(items):
            raise ValidationError("errors.invalid_percent")
        items[index] = items[index].model_copy(update={"percent": percent})
    else:
        category_name = data.get("pending_item_category")
        normalized = data.get("pending_item_normalized")
        if not category_name or not normalized:
            raise ValidationError("errors.invalid_manual_input")
        source_type = data.get("source_type", "manual")
        items.append(
            DraftCashbackItem(
                raw_category=category_name,
                normalized_category=normalized,
                percent=percent,
                source_type=source_type,
            )
        )
    await set_draft_items(state, items)
    await state.update_data(
        pending_action=None,
        editing_index=None,
        pending_item_category=None,
        pending_item_normalized=None,
    )
    await state.set_state(None)
    await show_preview_screen(message, state, db_user, app_container)


@router.callback_query(F.data == nav("save_bank"))
async def save_bank(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    data = await state.get_data()
    items = await get_draft_items(state)
    bank = await app_container.catalog_service.save_bank(
        session,
        db_user,
        bank_name=data.get("selected_bank_name", ""),
        items=items,
        source_type=data.get("source_type", "manual"),
        bank_id=data.get("selected_bank_id"),
    )
    details = await app_container.catalog_service.get_bank_details(session, db_user, bank.id)
    await clear_flow_data(state)
    draft_items = [
        DraftCashbackItem(
            raw_category=item.raw_category,
            normalized_category=item.normalized_category,
            percent=item.percent,
            source_type=item.source_type,
        )
        for item in details.items
    ]
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(
            db_user.language,
            "screens.bank_details",
            bank_name=details.bank_name,
            items=format_draft_items(app_container, db_user.language, draft_items),
        ),
        reply_markup=bank_details_keyboard(app_container.localizer, db_user.language, details.id),
    )


@router.callback_query(F.data == nav("cancel_add"))
async def cancel_preview(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await clear_flow_data(state)
    await show_home_screen(callback, state, db_user, app_container, screen_renderer)
