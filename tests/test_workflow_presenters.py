from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.application.presenters.workflow_formatters import (
    format_history_entries,
    format_items_lines,
    format_ranking,
    target_label,
)
from app.application.presenters.workflow_screens import (
    history_screen,
    interrupt_screen,
    preview_screen,
    settings_screen,
)
from app.application.workflow.models import WorkflowState
from app.domain.models import BankScore, CashbackDraftItem, CategoryLeader, UserAccount, UserLogEntry
from app.domain.services.categories import CategoryService


def test_preview_screen_produces_stable_transport_neutral_contract() -> None:
    categories = CategoryService()
    state = WorkflowState(
        selected_bank_name="T-Bank",
        draft_items=[
            CashbackDraftItem(
                raw_category="Fuel",
                normalized_category=categories.normalize("Fuel").slug,
                percent=Decimal("5"),
                source_type="manual",
            )
        ],
        temp_payload={"source_type": "manual"},
    )

    screen = preview_screen(state, "en", categories)

    assert screen.id == "preview"
    assert screen.title_key == "screens.preview"
    assert screen.body_key == "screens.preview"
    assert screen.body_params["bank_name"] == "T-Bank"
    assert screen.body_params["source_type"] == "manual"
    assert "Fuel: 5%" in str(screen.body_params["items"])
    assert [action.command for action in screen.actions[-3:]] == ["add_item", "save_bank", "cancel_flow"]


def test_interrupt_screen_hides_save_action_when_draft_cannot_be_saved() -> None:
    without_save = interrupt_screen(target_label_key="labels.target_home", can_save=False)
    with_save = interrupt_screen(target_label_key="labels.target_home", can_save=True)

    assert without_save.id == "interrupt_flow"
    assert without_save.layout_hint == "detail"
    assert [action.command for action in without_save.actions] == ["continue_draft", "discard_draft_and_go"]
    assert [action.command for action in with_save.actions] == [
        "continue_draft",
        "save_draft_and_go",
        "discard_draft_and_go",
    ]


def test_settings_and_history_screens_keep_expected_keys() -> None:
    user = UserAccount(id=1, display_name="Demo", language="ru", notifications_enabled=True)
    logs = [
        UserLogEntry(
            id=1,
            user_id=1,
            action="bank_added",
            payload=None,
            created_at=datetime(2026, 3, 11, 10, 15),
        )
    ]

    settings = settings_screen(user)
    history = history_screen(logs)

    assert settings.id == "settings"
    assert settings.body_params["notifications"] == "labels.notifications_on"
    assert settings.actions[0].command == "set_language"
    assert history.id == "history"
    assert "2026-03-11T10:15" in str(history.body_params["entries"])


def test_formatters_render_stable_strings_and_target_labels() -> None:
    categories = CategoryService()
    items = [
        CashbackDraftItem(
            raw_category="Fuel",
            normalized_category=categories.normalize("Fuel").slug,
            percent=Decimal("5"),
            source_type="manual",
        )
    ]
    logs = [
        UserLogEntry(
            id=1,
            user_id=1,
            action="draft_saved",
            payload=None,
            created_at=datetime(2026, 3, 11, 10, 15),
        )
    ]
    leaders = [CategoryLeader(category_slug="fuel", category_name="Fuel", best_percent=Decimal("7"), bank_names=["T-Bank"])]
    global_rating = [BankScore(bank_name="T-Bank", score=42)]

    assert format_items_lines(items, categories, "en") == "- Fuel / Fuel: 5%"
    assert format_history_entries(logs) == "- 2026-03-11T10:15 draft_saved"
    assert format_ranking(leaders, global_rating) == ("- Fuel: 7% (T-Bank)", "- T-Bank: 42")
    assert target_label("open_home") == "labels.target_home"
    assert target_label("unknown_command") == "labels.target_other"
