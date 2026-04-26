import pytest

from app.adapters.telegram.callbacks import decode_callback, encode_action
from app.application.models import Action
from app.domain.errors import ValidationError


def test_encode_decode_nav_bank() -> None:
    action = Action(command="open_bank", label_key="bank:T-Bank", payload={"id": 42})
    callback_data = encode_action(action)
    command = decode_callback(callback_data)
    assert callback_data == "nav:bank:42"
    assert command.name == "open_bank"
    assert command.payload["id"] == 42


def test_decode_nav_top_category() -> None:
    command = decode_callback("nav:top_category:fuel")
    assert command.name == "open_top_category"
    assert command.payload["slug"] == "fuel"


def test_input_method_callbacks_match_contract() -> None:
    manual_action = Action(
        command="choose_input_method", label_key="buttons.input_manual", payload={"method": "manual"}
    )
    photo_action = Action(
        command="choose_input_method", label_key="buttons.input_photo", payload={"method": "photo"}
    )
    template_action = Action(
        command="choose_input_method", label_key="buttons.input_template", payload={"method": "template"}
    )

    assert encode_action(manual_action) == "nav:input_manual"
    assert encode_action(photo_action) == "nav:input_photo"
    assert encode_action(template_action) == "nav:input_template"

    decoded_manual = decode_callback("nav:input_manual")
    decoded_photo = decode_callback("nav:input_photo")
    decoded_template = decode_callback("nav:input_template")
    assert decoded_manual.name == "choose_input_method"
    assert decoded_manual.payload["method"] == "manual"
    assert decoded_photo.name == "choose_input_method"
    assert decoded_photo.payload["method"] == "photo"
    assert decoded_template.name == "choose_input_method"
    assert decoded_template.payload["method"] == "template"


def test_decode_invalid_numeric_callback_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as info:
        decode_callback("nav:bank:not-a-number")
    assert info.value.message_key == "errors.unknown_command"


def test_all_core_screen_actions_have_callback_mapping() -> None:
    actions = [
        Action(command="open_home", label_key="buttons.home"),
        Action(command="open_add_bank", label_key="buttons.add_bank"),
        Action(command="select_bank_preset", label_key="bank:T-Bank", payload={"index": 0}),
        Action(command="select_bank_other", label_key="buttons.other_bank"),
        Action(command="choose_input_method", label_key="buttons.input_photo", payload={"method": "photo"}),
        Action(command="choose_input_method", label_key="buttons.input_manual", payload={"method": "manual"}),
        Action(
            command="choose_input_method", label_key="buttons.input_template", payload={"method": "template"}
        ),
        Action(command="open_preview", label_key="buttons.back"),
        Action(command="open_my_banks", label_key="buttons.my_banks"),
        Action(command="open_bank", label_key="bank:T-Bank", payload={"id": 1}),
        Action(command="open_settings", label_key="buttons.settings"),
        Action(command="set_language", label_key="buttons.language_ru", payload={"code": "ru"}),
        Action(command="toggle_notifications", label_key="buttons.toggle_notifications_off"),
        Action(command="open_top", label_key="buttons.top"),
        Action(command="open_top_category", label_key="АЗС", payload={"slug": "fuel"}),
        Action(command="pick_item", label_key="1. fuel", payload={"index": 0}),
        Action(command="edit_item_category", label_key="buttons.edit_category", payload={"index": 0}),
        Action(command="edit_item_percent", label_key="buttons.edit_percent", payload={"index": 0}),
        Action(command="delete_item", label_key="buttons.delete", payload={"index": 0}),
        Action(command="request_delete_bank", label_key="buttons.delete", payload={"id": 1}),
        Action(command="confirm_delete_bank", label_key="buttons.confirm_delete", payload={"id": 1}),
        Action(command="cancel_flow", label_key="buttons.cancel"),
        Action(command="add_item", label_key="buttons.add_item"),
        Action(command="save_bank", label_key="buttons.save"),
        Action(command="open_help", label_key="buttons.help"),
        Action(command="open_history", label_key="buttons.history"),
        Action(command="edit_bank", label_key="buttons.edit", payload={"id": 1}),
        Action(command="continue_draft", label_key="buttons.continue_editing"),
        Action(command="discard_draft_and_go", label_key="buttons.discard_and_continue"),
        Action(command="save_draft_and_go", label_key="buttons.save_and_continue"),
    ]

    for action in actions:
        callback_data = encode_action(action)
        command = decode_callback(callback_data)
        assert command.name == action.command
