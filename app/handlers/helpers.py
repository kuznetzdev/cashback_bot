from __future__ import annotations

from decimal import Decimal

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.keyboards.home import home_keyboard
from app.schemas.cashback_item import DraftCashbackItem


def source_label(localizer, language: str, source_type: str) -> str:
    return localizer.gettext(language, f"labels.source_{source_type}")


def format_draft_items(
    container: AppContainer,
    language: str,
    items: list[DraftCashbackItem],
) -> str:
    if not items:
        return "—"
    lines = []
    for index, item in enumerate(items, start=1):
        title = container.category_service.display_name(item.normalized_category, language)
        lines.append(f"{index}. {title} / {item.raw_category} — {item.percent}%")
    return "\n".join(lines)


def format_percent(value: Decimal | str | float | int) -> str:
    number = Decimal(str(value)).normalize()
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


async def show_home_screen(
    event: Message | CallbackQuery,
    state: FSMContext,
    db_user,
    app_container: AppContainer,
    screen_renderer: TelegramScreenRenderer,
) -> None:
    language = db_user.language
    await screen_renderer.show_screen(
        event,
        state,
        app_container.localizer.gettext(language, "screens.home"),
        reply_markup=home_keyboard(app_container.localizer, language),
    )
