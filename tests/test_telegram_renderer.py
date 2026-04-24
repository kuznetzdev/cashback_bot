from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Message

from app.adapters.telegram.renderer import TelegramScreenRenderer
from app.application.workflow.models import Action, Screen
from app.i18n.localizer import Localizer


def _build_renderer() -> TelegramScreenRenderer:
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    return TelegramScreenRenderer(localizer=Localizer(locales_dir=locales_dir, default_language="en"))


@dataclass
class DummyState:
    data: dict[str, object] = field(default_factory=dict)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def update_data(self, **kwargs: object) -> None:
        self.data.update(kwargs)


def _build_message_event(message_id: int = 10) -> Message:
    bot = Bot("123456:valid_token")
    return Message.model_validate(
        {
            "message_id": message_id,
            "date": 0,
            "chat": {"id": 77, "type": "private"},
            "from": {"id": 11, "is_bot": False, "first_name": "Demo"},
            "text": "hello",
        },
        context={"bot": bot},
    )


def _build_callback_event(message_id: int = 99) -> CallbackQuery:
    bot = Bot("123456:valid_token")
    return CallbackQuery.model_validate(
        {
            "id": "cbq-1",
            "from": {"id": 11, "is_bot": False, "first_name": "Demo"},
            "chat_instance": "instance-1",
            "data": "nav:home",
            "message": {
                "message_id": message_id,
                "date": 0,
                "chat": {"id": 77, "type": "private"},
                "from": {"id": 123456, "is_bot": True, "first_name": "Bot"},
                "text": "menu",
            },
        },
        context={"bot": bot},
    )


def test_renderer_builds_keyboard_from_screen_actions() -> None:
    renderer = _build_renderer()
    screen = Screen(
        id="input_method",
        title_key="screens.input_method",
        body_key="screens.input_method",
        body_params={"bank_name": "T-Bank"},
        actions=[Action(command="choose_input_method", label_key="buttons.input_manual", payload={"method": "manual"})],
    )
    keyboard = renderer._build_keyboard(screen, "en")
    assert keyboard is not None
    assert keyboard.inline_keyboard[0][0].text == "Manual"
    assert keyboard.inline_keyboard[0][0].callback_data == "nav:input_manual"


def test_renderer_resolves_nested_locale_keys_in_body_params() -> None:
    renderer = _build_renderer()
    screen = Screen(
        id="settings",
        title_key="screens.settings",
        body_key="screens.settings",
        body_params={"language": "labels.language_en", "notifications": "labels.notifications_on"},
    )
    text = renderer._render_screen_text(screen, "en")
    assert "Language: English" in text
    assert "Notifications: enabled" in text


def test_renderer_does_not_duplicate_text_for_same_title_and_body_key() -> None:
    renderer = _build_renderer()
    screen = Screen(id="home", title_key="screens.home", body_key="screens.home")
    text = renderer._render_screen_text(screen, "en")
    assert text.count("Cashback Analyzer") == 1


@pytest.mark.asyncio()
async def test_renderer_sends_fresh_message_for_user_message_and_replaces_previous_screen(monkeypatch) -> None:
    renderer = _build_renderer()
    state = DummyState({"last_screen_message_id": 41})
    screen = Screen(id="home", title_key="screens.home", body_key="screens.home")
    event = _build_message_event()
    deleted: list[int] = []

    async def fake_send_message(*, bot, chat_id, text, markup=None):
        _ = (bot, chat_id, text, markup)
        return SimpleNamespace(message_id=105)

    async def fake_delete_message(bot, chat_id, message_id):
        _ = (bot, chat_id)
        deleted.append(message_id)

    monkeypatch.setattr(renderer, "_send_message", fake_send_message)
    monkeypatch.setattr(renderer, "_edit_message_text", AsyncMock(side_effect=AssertionError("should not edit old screen on message event")))
    monkeypatch.setattr(TelegramScreenRenderer, "_safe_delete_message", staticmethod(fake_delete_message))

    await renderer.render(event=event, state=state, screen=screen, language="en")

    assert state.data["last_screen_message_id"] == 105
    assert deleted == [41]


@pytest.mark.asyncio()
async def test_renderer_edits_existing_message_for_callback_query(monkeypatch) -> None:
    renderer = _build_renderer()
    state = DummyState({"last_screen_message_id": 99})
    screen = Screen(id="home", title_key="screens.home", body_key="screens.home")
    event = _build_callback_event()

    monkeypatch.setattr(renderer, "_send_message", AsyncMock(side_effect=AssertionError("callback flow should edit existing message")))
    monkeypatch.setattr(renderer, "_edit_message_text", AsyncMock(return_value=True))
    monkeypatch.setattr(renderer, "_safe_answer_callback", AsyncMock())
    monkeypatch.setattr(renderer, "_safe_delete_callback_source", AsyncMock())

    await renderer.render(event=event, state=state, screen=screen, language="en")

    assert state.data["last_screen_message_id"] == 99
    renderer._edit_message_text.assert_awaited_once()
