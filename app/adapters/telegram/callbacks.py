from __future__ import annotations

from app.application.workflow.models import Action, UserCommand
from app.domain.errors import ValidationError


def encode_action(action: Action) -> str:
    command = action.command
    payload = action.payload
    if command == "open_home":
        return "nav:home"
    if command == "open_add_bank":
        return "nav:add_bank"
    if command == "select_existing_bank":
        return f"nav:existing_bank:{int(payload['id'])}"
    if command == "select_bank_preset":
        return f"nav:add_bank_select:{int(payload['index'])}"
    if command == "select_bank_other":
        return "nav:add_bank_select:other"
    if command == "choose_input_method":
        method = str(payload["method"])
        if method == "photo":
            return "nav:input_photo"
        if method == "manual":
            return "nav:input_manual"
        if method == "template":
            return "nav:input_template"
        raise ValidationError("errors.unknown_command")
    if command == "open_preview":
        return "nav:preview"
    if command == "open_my_banks":
        return "nav:my_banks"
    if command == "open_bank":
        if "month" in payload:
            return f"nav:bank:{int(payload['id'])}:{str(payload['month'])}"
        return f"nav:bank:{int(payload['id'])}"
    if command == "open_settings":
        return "nav:settings"
    if command == "set_language":
        return f"nav:set_lang:{str(payload['code'])}"
    if command == "toggle_notifications":
        return "nav:toggle_notifications"
    if command == "open_top":
        return "nav:top"
    if command == "open_top_category":
        return f"nav:top_category:{str(payload['slug'])}"
    if command == "pick_item":
        return f"nav:edit_item:{int(payload['index'])}"
    if command == "edit_item_category":
        return f"nav:edit_category:{int(payload['index'])}"
    if command == "edit_item_percent":
        return f"nav:edit_percent:{int(payload['index'])}"
    if command == "delete_item":
        return f"nav:delete_item:{int(payload['index'])}"
    if command == "request_delete_bank":
        return f"nav:delete_bank:{int(payload['id'])}"
    if command == "confirm_delete_bank":
        return f"nav:confirm_delete_bank:{int(payload['id'])}"
    if command == "cancel_flow":
        return "nav:cancel_add"
    if command == "add_item":
        return "nav:add_item"
    if command == "change_selected_bank":
        return "nav:change_bank"
    if command == "set_target_month":
        return f"nav:set_month:{int(payload['offset'])}"
    if command == "save_bank":
        return "nav:save_bank"
    if command == "open_help":
        return "nav:help"
    if command == "open_history":
        return "nav:history"
    if command == "edit_bank":
        return f"nav:edit_bank:{int(payload['id'])}"
    if command == "continue_draft":
        return "nav:continue_draft"
    if command == "discard_draft_and_go":
        return "nav:discard_draft"
    if command == "save_draft_and_go":
        return "nav:save_draft_and_go"
    raise ValidationError("errors.unknown_command")


def decode_callback(callback_data: str) -> UserCommand:
    parts = callback_data.split(":")
    if len(parts) < 2 or parts[0] != "nav":
        raise ValidationError("errors.unknown_command")
    scope = parts[1]

    if scope == "home":
        return UserCommand(name="open_home")
    if scope == "add_bank":
        return UserCommand(name="open_add_bank")
    if scope == "existing_bank" and len(parts) >= 3:
        return UserCommand(name="select_existing_bank", payload={"id": _parse_int(parts[2])})
    if scope == "add_bank_select":
        if len(parts) < 3:
            raise ValidationError("errors.unknown_command")
        if parts[2] == "other":
            return UserCommand(name="select_bank_other")
        return UserCommand(name="select_bank_preset", payload={"index": _parse_int(parts[2])})
    if scope == "input_photo":
        return UserCommand(name="choose_input_method", payload={"method": "photo"})
    if scope == "input_manual":
        return UserCommand(name="choose_input_method", payload={"method": "manual"})
    if scope == "input_template":
        return UserCommand(name="choose_input_method", payload={"method": "template"})
    if scope == "input_method" and len(parts) >= 3:
        return UserCommand(name="choose_input_method", payload={"method": parts[2]})
    if scope == "preview":
        return UserCommand(name="open_preview")
    if scope == "my_banks":
        return UserCommand(name="open_my_banks")
    if scope == "bank" and len(parts) >= 3:
        payload: dict[str, object] = {"id": _parse_int(parts[2])}
        if len(parts) >= 4:
            payload["month"] = parts[3]
        return UserCommand(name="open_bank", payload=payload)
    if scope == "settings":
        return UserCommand(name="open_settings")
    if scope == "set_lang" and len(parts) >= 3:
        return UserCommand(name="set_language", payload={"code": parts[2]})
    if scope == "toggle_notifications":
        return UserCommand(name="toggle_notifications")
    if scope == "top":
        return UserCommand(name="open_top")
    if scope == "top_category" and len(parts) >= 3:
        slug = ":".join(parts[2:])
        return UserCommand(name="open_top_category", payload={"slug": slug})
    if scope == "edit_item" and len(parts) >= 3:
        return UserCommand(name="pick_item", payload={"index": _parse_int(parts[2])})
    if scope == "edit_category" and len(parts) >= 3:
        return UserCommand(name="edit_item_category", payload={"index": _parse_int(parts[2])})
    if scope == "edit_percent" and len(parts) >= 3:
        return UserCommand(name="edit_item_percent", payload={"index": _parse_int(parts[2])})
    if scope == "delete_item" and len(parts) >= 3:
        return UserCommand(name="delete_item", payload={"index": _parse_int(parts[2])})
    if scope == "delete_bank" and len(parts) >= 3:
        return UserCommand(name="request_delete_bank", payload={"id": _parse_int(parts[2])})
    if scope == "confirm_delete_bank" and len(parts) >= 3:
        return UserCommand(name="confirm_delete_bank", payload={"id": _parse_int(parts[2])})
    if scope == "cancel_add":
        return UserCommand(name="cancel_flow")
    if scope == "add_item":
        return UserCommand(name="add_item")
    if scope == "change_bank":
        return UserCommand(name="change_selected_bank")
    if scope == "set_month" and len(parts) >= 3:
        return UserCommand(name="set_target_month", payload={"offset": _parse_int(parts[2])})
    if scope == "save_bank":
        return UserCommand(name="save_bank")
    if scope == "help":
        return UserCommand(name="open_help")
    if scope == "history":
        return UserCommand(name="open_history")
    if scope == "edit_bank" and len(parts) >= 3:
        return UserCommand(name="edit_bank", payload={"id": _parse_int(parts[2])})
    if scope == "continue_draft":
        return UserCommand(name="continue_draft")
    if scope == "discard_draft":
        return UserCommand(name="discard_draft_and_go")
    if scope == "save_draft_and_go":
        return UserCommand(name="save_draft_and_go")
    raise ValidationError("errors.unknown_command")


def _parse_int(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as error:
        raise ValidationError("errors.unknown_command") from error
