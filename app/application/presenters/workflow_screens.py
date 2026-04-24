from __future__ import annotations

from app.application.presenters.workflow_formatters import (
    format_history_entries,
    format_items_lines,
    format_ranking,
)
from app.application.workflow.models import Action, Effect, Screen, WorkflowResult, WorkflowState
from app.domain.models import Bank, BankAggregate, BankScore, CashbackDraftItem, CategoryLeader, UserAccount, UserLogEntry
from app.domain.services.categories import CategoryService


def result_with_screen(
    *,
    user: UserAccount,
    state: WorkflowState,
    screen: Screen,
    effects: list[Effect] | None = None,
) -> WorkflowResult:
    return WorkflowResult(user=user, state=state, screen=screen, effects=effects or [])


def home_screen(body_key: str = "screens.home") -> Screen:
    return Screen(
        id="home",
        title_key="screens.home",
        body_key=body_key,
        actions=[
            Action(command="open_add_bank", label_key="buttons.add_bank"),
            Action(command="open_my_banks", label_key="buttons.my_banks"),
            Action(command="open_top", label_key="buttons.top"),
            Action(command="open_settings", label_key="buttons.settings"),
            Action(command="open_history", label_key="buttons.history"),
            Action(command="open_help", label_key="buttons.help"),
        ],
    )


def help_screen() -> Screen:
    return Screen(
        id="help",
        title_key="screens.help",
        body_key="screens.help",
        actions=[Action(command="open_home", label_key="buttons.home")],
    )


def choose_bank_screen(popular_banks: list[str]) -> Screen:
    actions = [Action(command="select_bank_preset", label_key=name, payload={"index": idx}) for idx, name in enumerate(popular_banks)]
    actions.append(Action(command="select_bank_other", label_key="buttons.other_bank"))
    actions.append(Action(command="open_home", label_key="buttons.home"))
    return Screen(id="choose_bank", title_key="screens.choose_bank", body_key="screens.choose_bank", actions=actions)


def custom_bank_prompt_screen() -> Screen:
    return Screen(
        id="custom_bank_name",
        title_key="screens.enter_bank_name",
        body_key="screens.enter_bank_name",
        actions=[Action(command="cancel_flow", label_key="buttons.cancel")],
        expects_input="custom_bank_name",
    )


def input_method_screen(bank_name: str) -> Screen:
    return Screen(
        id="input_method",
        title_key="screens.input_method",
        body_key="screens.input_method",
        body_params={"bank_name": bank_name},
        actions=[
            Action(command="choose_input_method", label_key="buttons.input_photo", payload={"method": "photo"}),
            Action(command="choose_input_method", label_key="buttons.input_manual", payload={"method": "manual"}),
            Action(command="choose_input_method", label_key="buttons.input_template", payload={"method": "template"}),
            Action(command="cancel_flow", label_key="buttons.cancel"),
        ],
    )


def manual_prompt_screen() -> Screen:
    return Screen(
        id="manual_prompt",
        title_key="screens.manual_prompt",
        body_key="screens.manual_prompt",
        actions=[Action(command="cancel_flow", label_key="buttons.cancel")],
        expects_input="manual_lines",
    )


def photo_prompt_screen() -> Screen:
    return Screen(
        id="photo_prompt",
        title_key="screens.photo_prompt",
        body_key="screens.photo_prompt",
        actions=[Action(command="cancel_flow", label_key="buttons.cancel")],
        expects_input="photo_upload",
    )


def preview_screen(state: WorkflowState, language: str, categories: CategoryService) -> Screen:
    actions = [
        Action(command="pick_item", label_key=f"{idx + 1}. {item.raw_category} ({item.percent}%)", payload={"index": idx})
        for idx, item in enumerate(state.draft_items)
    ]
    actions.extend(
        [
            Action(command="add_item", label_key="buttons.add_item"),
            Action(command="save_bank", label_key="buttons.save"),
            Action(command="cancel_flow", label_key="buttons.cancel"),
        ]
    )
    source_type = state.temp_payload.get("source_type", "manual")
    return Screen(
        id="preview",
        title_key="screens.preview",
        body_key="screens.preview",
        body_params={
            "bank_name": state.selected_bank_name or "-",
            "items": format_items_lines(state.draft_items, categories, language),
            "source_type": source_type,
        },
        actions=actions,
    )


def edit_item_screen(item: CashbackDraftItem, idx: int) -> Screen:
    return Screen(
        id="edit_item",
        title_key="screens.choose_item_action",
        body_key="screens.choose_item_action",
        body_params={"item": item.raw_category, "percent": item.percent},
        actions=[
            Action(command="edit_item_category", label_key="buttons.edit_category", payload={"index": idx}),
            Action(command="edit_item_percent", label_key="buttons.edit_percent", payload={"index": idx}),
            Action(command="delete_item", label_key="buttons.delete", payload={"index": idx}, destructive=True),
            Action(command="open_preview", label_key="buttons.back"),
        ],
    )


def item_category_prompt_screen() -> Screen:
    return Screen(
        id="item_category_prompt",
        title_key="screens.ask_item_category",
        body_key="screens.ask_item_category",
        actions=[Action(command="open_preview", label_key="buttons.back")],
        expects_input="item_category",
    )


def item_percent_prompt_screen() -> Screen:
    return Screen(
        id="item_percent_prompt",
        title_key="screens.ask_item_percent",
        body_key="screens.ask_item_percent",
        actions=[Action(command="open_preview", label_key="buttons.back")],
        expects_input="item_percent",
    )


def settings_screen(user: UserAccount) -> Screen:
    notifications = "labels.notifications_on" if user.notifications_enabled else "labels.notifications_off"
    language = "labels.language_en" if user.language == "en" else "labels.language_ru"
    toggle_key = "buttons.toggle_notifications_on" if user.notifications_enabled else "buttons.toggle_notifications_off"
    return Screen(
        id="settings",
        title_key="screens.settings",
        body_key="screens.settings",
        body_params={"language": language, "notifications": notifications},
        actions=[
            Action(command="set_language", label_key="buttons.language_ru", payload={"code": "ru"}),
            Action(command="set_language", label_key="buttons.language_en", payload={"code": "en"}),
            Action(command="toggle_notifications", label_key=toggle_key),
            Action(command="open_home", label_key="buttons.home"),
        ],
    )


def interrupt_screen(*, target_label_key: str, can_save: bool) -> Screen:
    actions = [Action(command="continue_draft", label_key="buttons.continue_editing", variant="secondary", group="safe")]
    if can_save:
        actions.append(Action(command="save_draft_and_go", label_key="buttons.save_and_continue", variant="primary", group="safe"))
    actions.append(
        Action(
            command="discard_draft_and_go",
            label_key="buttons.discard_and_continue",
            destructive=True,
            variant="danger",
            group="danger",
        )
    )
    return Screen(
        id="interrupt_flow",
        title_key="screens.interrupt_flow",
        body_key="messages.confirm_discard_draft",
        body_params={"target": target_label_key},
        actions=actions,
        layout_hint="detail",
    )


def my_banks_screen(banks: list[Bank]) -> Screen:
    if not banks:
        return Screen(
            id="my_banks",
            title_key="screens.my_banks",
            body_key="messages.empty_banks",
            actions=[Action(command="open_home", label_key="buttons.home")],
        )
    actions = [Action(command="open_bank", label_key=f"bank:{item.bank_name}", payload={"id": item.id}) for item in banks]
    actions.append(Action(command="open_home", label_key="buttons.home"))
    return Screen(id="my_banks", title_key="screens.my_banks", body_key="screens.my_banks", actions=actions)


def bank_details_screen(aggregate: BankAggregate, language: str, categories: CategoryService) -> Screen:
    return Screen(
        id="bank_details",
        title_key="screens.bank_details",
        body_key="screens.bank_details",
        body_params={
            "bank_name": aggregate.bank.bank_name,
            "items": format_items_lines(aggregate.items, categories, language),
        },
        actions=[
            Action(command="edit_bank", label_key="buttons.edit", payload={"id": aggregate.bank.id}),
            Action(command="request_delete_bank", label_key="buttons.delete", payload={"id": aggregate.bank.id}, destructive=True),
            Action(command="open_home", label_key="buttons.home"),
        ],
    )


def confirm_delete_bank_screen(aggregate: BankAggregate) -> Screen:
    return Screen(
        id="confirm_delete_bank",
        title_key="screens.confirm_delete_bank",
        body_key="screens.confirm_delete_bank",
        body_params={"bank_name": aggregate.bank.bank_name},
        actions=[
            Action(command="confirm_delete_bank", label_key="buttons.confirm_delete", payload={"id": aggregate.bank.id}, destructive=True),
            Action(command="open_bank", label_key="buttons.back", payload={"id": aggregate.bank.id}),
        ],
    )


def top_screen(leaders: list[CategoryLeader], global_rating: list[BankScore]) -> Screen:
    if not leaders:
        # Empty-state onboarding: instead of a dead-end "no data" screen,
        # invite the user into the add-bank flow so /top is productive even
        # on a fresh account.
        return Screen(
            id="top",
            title_key="screens.top",
            body_key="messages.no_ranking_data_onboarding",
            actions=[
                Action(command="open_add_bank", label_key="buttons.add_bank"),
                Action(command="open_home", label_key="buttons.home"),
            ],
        )
    leaders_text, global_text = format_ranking(leaders, global_rating)
    actions = [Action(command="open_top_category", label_key=item.category_name, payload={"slug": item.category_slug}) for item in leaders]
    actions.append(Action(command="open_home", label_key="buttons.home"))
    return Screen(
        id="top",
        title_key="screens.top",
        body_key="screens.top",
        body_params={"leaders": leaders_text, "global_rating": global_text},
        actions=actions,
    )


def top_category_screen(leader: CategoryLeader | None) -> Screen:
    if leader is None:
        # Offer an Add-bank CTA so a user who asked "best card for X" but has
        # nothing configured can act on the answer immediately, instead of
        # having to find the add-bank entry point themselves.
        return Screen(
            id="top_category",
            title_key="screens.top_category",
            body_key="messages.no_ranking_data",
            actions=[
                Action(command="open_add_bank", label_key="buttons.add_bank"),
                Action(command="open_top", label_key="buttons.back"),
                Action(command="open_home", label_key="buttons.home"),
            ],
        )
    return Screen(
        id="top_category",
        title_key="screens.top_category",
        body_key="screens.top_category",
        body_params={"category": leader.category_name, "percent": leader.best_percent, "banks": ", ".join(leader.bank_names)},
        actions=[Action(command="open_top", label_key="buttons.back"), Action(command="open_home", label_key="buttons.home")],
    )


def history_screen(logs: list[UserLogEntry]) -> Screen:
    if not logs:
        return Screen(
            id="history",
            title_key="screens.history",
            body_key="messages.empty_history",
            actions=[Action(command="open_home", label_key="buttons.home")],
        )
    return Screen(
        id="history",
        title_key="screens.history",
        body_key="screens.history",
        body_params={"entries": format_history_entries(logs)},
        actions=[Action(command="open_home", label_key="buttons.home")],
    )


def delete_category_result_screen(count: int, banks: int) -> Screen:
    return Screen(
        id="delete_category_result",
        title_key="screens.home",
        body_key="messages.deleted_category",
        body_params={"count": count, "banks": banks},
        actions=[Action(command="open_home", label_key="buttons.home")],
    )
