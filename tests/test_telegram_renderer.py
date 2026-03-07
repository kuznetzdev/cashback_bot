from __future__ import annotations

from pathlib import Path

from app.adapters.telegram.localizer import Localizer
from app.adapters.telegram.renderer import TelegramScreenRenderer
from app.application.models import Action, Screen


def _build_renderer() -> TelegramScreenRenderer:
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    return TelegramScreenRenderer(localizer=Localizer(locales_dir=locales_dir, default_language="en"))


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
