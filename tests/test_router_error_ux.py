from __future__ import annotations

from app.adapters.telegram.router import (
    _OCR_RETRYABLE_KEYS,
    _home_action,
    _recovery_actions,
    _resolve_start_payload,
)
from app.application.models import UserCommand


def test_home_action_points_to_open_home_with_localized_label() -> None:
    action = _home_action()
    assert action.command == "open_home"
    assert action.label_key == "buttons.home"


def test_recovery_always_includes_home_button() -> None:
    actions = _recovery_actions("errors.invalid_bank_name", UserCommand(name="submit_custom_bank_name"))
    assert any(a.command == "open_home" for a in actions), (
        "Every error MUST expose a Home button — no text-only dead-ends."
    )


def test_recovery_for_ocr_timeout_adds_retry_button() -> None:
    actions = _recovery_actions("errors.ocr_timeout", UserCommand(name="submit_uploaded_image"))
    commands = [a.command for a in actions]
    assert "open_add_bank" in commands, "Retry button must let the user start a new bank flow"
    assert "open_home" in commands


def test_recovery_for_broken_image_adds_retry_button() -> None:
    actions = _recovery_actions("errors.broken_image", UserCommand(name="submit_uploaded_image"))
    commands = [a.command for a in actions]
    assert "open_add_bank" in commands
    assert "open_home" in commands


def test_recovery_for_upload_command_adds_retry_even_on_unlisted_error() -> None:
    # If the upload path itself raises something unusual, still offer a retry
    # route so the user can switch to manual input without leaving the draft flow.
    actions = _recovery_actions("errors.unexpected", UserCommand(name="submit_uploaded_image"))
    commands = [a.command for a in actions]
    assert "open_add_bank" in commands
    assert "open_home" in commands


def test_recovery_for_plain_command_error_stays_minimal() -> None:
    # A validation error during settings toggle shouldn't spawn an unrelated
    # "Try again with another bank" button — only the Home escape.
    actions = _recovery_actions("errors.invalid_language", UserCommand(name="set_language"))
    commands = [a.command for a in actions]
    assert commands == ["open_home"]


def test_ocr_retryable_keys_covers_all_three_documented_error_keys() -> None:
    # Keep the retryable set in sync with the keys raised by TesseractOCRAdapter
    # and OpenAIVisionOCRAdapter so the retry button is offered when appropriate.
    assert {
        "errors.ocr_timeout",
        "errors.ocr_empty",
        "errors.broken_image",
    } == _OCR_RETRYABLE_KEYS


def test_deep_link_payload_inline_setup_opens_add_bank() -> None:
    command = _resolve_start_payload("inline_setup")
    assert command.name == "open_add_bank"


def test_deep_link_payload_inline_goes_home() -> None:
    # Plain "inline" (clicked on an onboarding result without specific intent)
    # should land on the normal home screen.
    command = _resolve_start_payload("inline")
    assert command.name == "start"


def test_deep_link_unknown_payload_falls_back_to_start() -> None:
    command = _resolve_start_payload("garbage")
    assert command.name == "start"


def test_deep_link_empty_payload_returns_start() -> None:
    command = _resolve_start_payload("")
    assert command.name == "start"
