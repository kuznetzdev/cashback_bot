from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SourceType
from app.core.exceptions import FileTooLargeError, UnsupportedFileError, ValidationError
from app.db.models import User
from app.handlers.helpers import show_home_screen
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_files import download_telegram_file
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.input_flow import input_method_keyboard
from app.schemas.cashback_item import DraftCashbackItem
from app.utils.callback import nav
from app.utils.files import cleanup_file
from app.utils.state import InputStates, clear_flow_data, set_draft_items

router = Router(name="input_flow")


async def _show_input_method(
    event: Message | CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    data = await state.get_data()
    bank_name = data["selected_bank_name"]
    await screen_renderer.show_screen(
        event,
        state,
        app_container.localizer.gettext(db_user.language, "screens.input_method", bank_name=bank_name),
        reply_markup=input_method_keyboard(app_container.localizer, db_user.language),
    )


@router.message(InputStates.waiting_custom_bank_name, F.text)
async def custom_bank_name(
    message: Message,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    bank_name = (message.text or "").strip()
    if not bank_name:
        raise ValidationError("errors.invalid_bank_name")
    await state.update_data(selected_bank_name=bank_name, selected_bank_id=None, flow_origin="create")
    await state.set_state(None)
    await _show_input_method(message, state, db_user, app_container, screen_renderer)


@router.callback_query(F.data == nav("input_manual"))
async def input_manual(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await state.update_data(source_type=SourceType.MANUAL.value)
    await state.set_state(InputStates.waiting_manual_lines)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.manual_prompt"),
    )


@router.callback_query(F.data == nav("input_photo"))
async def input_photo(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await state.update_data(source_type=SourceType.OCR.value)
    await state.set_state(InputStates.waiting_photo)
    await screen_renderer.show_screen(
        callback,
        state,
        app_container.localizer.gettext(db_user.language, "screens.photo_prompt"),
    )


@router.callback_query(F.data == nav("input_template"))
async def input_template(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
) -> None:
    from app.handlers.preview import show_preview_screen

    items = [
        DraftCashbackItem(
            raw_category=app_container.category_service.display_name(slug, db_user.language),
            normalized_category=slug,
            percent=0,
            source_type=SourceType.TEMPLATE.value,
        )
        for slug in app_container.category_service.template_slugs()
    ]
    await state.update_data(source_type=SourceType.TEMPLATE.value)
    await set_draft_items(state, items)
    await state.set_state(None)
    await show_preview_screen(callback, state, db_user, app_container)


@router.message(InputStates.waiting_manual_lines, F.text)
async def receive_manual_lines(
    message: Message,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
) -> None:
    from app.handlers.preview import show_preview_screen

    items = app_container.parser_service.parse_manual_lines(message.text or "")
    await set_draft_items(state, items)
    await state.set_state(None)
    await show_preview_screen(message, state, db_user, app_container)


@router.message(InputStates.waiting_photo, F.photo | F.document)
async def receive_photo(
    message: Message,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    from app.handlers.preview import show_preview_screen

    file_id: str | None = None
    file_size = 0
    suffix = ".jpg"
    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_size = photo.file_size or 0
        suffix = ".jpg"
    elif message.document:
        if not (message.document.mime_type or "").startswith("image/"):
            raise UnsupportedFileError()
        file_id = message.document.file_id
        file_size = message.document.file_size or 0
        suffix = ".png"

    if file_id is None:
        raise ValidationError("errors.send_photo_or_text")
    if file_size > app_container.settings.max_file_size:
        raise FileTooLargeError(app_container.settings.max_file_size)

    status_message = await screen_renderer.send_status(
        message,
        app_container.localizer.gettext(db_user.language, "messages.processing"),
    )
    temp_path = None
    try:
        temp_path = await download_telegram_file(message.bot, file_id, suffix, app_container.settings.temp_dir)
        text = await app_container.ocr_service.extract_text(temp_path)
        items = app_container.parser_service.parse_ocr_text(text)
        if not items:
            raise ValidationError("errors.ocr_empty")
        await set_draft_items(state, items)
        await state.set_state(None)
        await show_preview_screen(message, state, db_user, app_container)
    finally:
        cleanup_file(temp_path)
        await screen_renderer.delete_message_best_effort(message.bot, status_message.chat.id, status_message.message_id)


@router.callback_query(F.data == nav("cancel_add"))
async def cancel_add(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    await clear_flow_data(state)
    await show_home_screen(callback, state, db_user, app_container, screen_renderer)
