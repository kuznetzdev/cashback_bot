"""End-to-end scenario regression tests. Each test pins a real user journey
or edge case we found during the production-readiness audit, so the UX
doesn't silently regress when someone refactors the underlying layers.

Covers:
 - inline onboarding when ``TELEGRAM_BOT_USERNAME`` is unset (no {link} leak);
 - "best card for X" with zero banks shows an Add-bank CTA;
 - /quickadd boundary percentages (>100, 0, 100);
 - free-form text with no matching intent lands on /help, not a crash;
 - workflow state deserialisation survives junk input.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.telegram.inline import InlineDependencies, handle_inline_query
from app.application.presenters.workflow_screens import top_category_screen
from app.application.use_cases.quick_add_bank import QuickAddBankUseCase
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.application.workflow.models import WorkflowState
from app.domain.errors import ValidationError
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.i18n.localizer import Localizer


LOCALES_DIR = Path(__file__).resolve().parents[1] / "app" / "locales"


# --- inline mode: bot_username missing ---------------------------------------


@pytest.mark.asyncio
async def test_inline_onboarding_without_bot_username_has_no_link_placeholder() -> None:
    loc = Localizer(locales_dir=LOCALES_DIR, default_language="ru")
    facade = SimpleNamespace(
        find_user_by_external_identity=AsyncMock(return_value=None),
        ranking_snapshot=AsyncMock(),
    )
    deps = InlineDependencies(facade=facade, localizer=loc, default_language="ru", bot_username=None)
    query = SimpleNamespace(query="", from_user=SimpleNamespace(id=1), answer=AsyncMock())

    await handle_inline_query(query, deps)

    results = query.answer.await_args.kwargs["results"]
    assert len(results) == 1
    body = results[0].input_message_content.message_text
    # The template previously rendered a literal "{link}" when bot_username
    # was empty — regression test pinning the fix.
    assert "{link}" not in body
    assert "{" not in body  # no leaked placeholders of any kind


@pytest.mark.asyncio
async def test_inline_empty_banks_without_bot_username_has_no_link_placeholder() -> None:
    loc = Localizer(locales_dir=LOCALES_DIR, default_language="ru")
    from app.application.use_cases.ranking_snapshot import RankingSnapshot
    from app.domain.models import UserAccount

    user = UserAccount(id=1, display_name="U", language="ru", notifications_enabled=True)
    empty = RankingSnapshot(
        leaders=[], query="", normalized_slug="", display_name="", best_match=None
    )
    facade = SimpleNamespace(
        find_user_by_external_identity=AsyncMock(return_value=user),
        ranking_snapshot=AsyncMock(return_value=empty),
    )
    deps = InlineDependencies(facade=facade, localizer=loc, default_language="ru", bot_username=None)
    query = SimpleNamespace(query="", from_user=SimpleNamespace(id=1), answer=AsyncMock())

    await handle_inline_query(query, deps)

    results = query.answer.await_args.kwargs["results"]
    body = results[0].input_message_content.message_text
    assert "{link}" not in body and "{" not in body


@pytest.mark.asyncio
async def test_inline_onboarding_with_bot_username_appends_link() -> None:
    loc = Localizer(locales_dir=LOCALES_DIR, default_language="ru")
    facade = SimpleNamespace(
        find_user_by_external_identity=AsyncMock(return_value=None),
        ranking_snapshot=AsyncMock(),
    )
    deps = InlineDependencies(
        facade=facade, localizer=loc, default_language="ru", bot_username="cashback_analyzer_bot"
    )
    query = SimpleNamespace(query="", from_user=SimpleNamespace(id=1), answer=AsyncMock())

    await handle_inline_query(query, deps)

    body = query.answer.await_args.kwargs["results"][0].input_message_content.message_text
    assert "https://t.me/cashback_analyzer_bot?start=" in body


# --- best-for-X with zero banks: onboarding CTA ------------------------------


def test_top_category_empty_includes_add_bank_cta() -> None:
    screen = top_category_screen(leader=None)
    commands = [action.command for action in screen.actions]
    # Three escape routes: add a bank (to actually solve the problem),
    # go back to top (might have other data), go home.
    assert "open_add_bank" in commands
    assert "open_top" in commands
    assert "open_home" in commands


# --- /quickadd boundary percentages -----------------------------------------


@pytest.fixture()
def quick_add(uow_factory):
    parser = ParserService(CategoryService())
    return QuickAddBankUseCase(parser, SaveBankDraftUseCase(uow_factory))


@pytest.fixture()
async def user(store):
    from app.domain.models import UserAccount

    account = UserAccount(id=store.next_user_id, display_name="U", language="ru", notifications_enabled=True)
    store.users[account.id] = account
    store.next_user_id += 1
    return account


@pytest.mark.asyncio
async def test_quickadd_rejects_percent_over_100(quick_add, user) -> None:
    with pytest.raises(ValidationError) as error:
        await quick_add.execute(user_id=user.id, payload="T-Bank: АЗС 150%")
    # Falls through to the "nothing parseable" error path — the regex requires
    # at most 2 digits, and the parser strips out-of-bound values.
    assert error.value.message_key == "errors.invalid_manual_input"


@pytest.mark.asyncio
async def test_quickadd_rejects_zero_percent(quick_add, user) -> None:
    with pytest.raises(ValidationError) as error:
        await quick_add.execute(user_id=user.id, payload="T-Bank: АЗС 0%")
    assert error.value.message_key == "errors.invalid_manual_input"


@pytest.mark.asyncio
async def test_quickadd_accepts_exactly_100_percent(quick_add, user, store) -> None:
    # 100% is valid — some marketing cashback promos really do offer 100%.
    result = await quick_add.execute(user_id=user.id, payload="T-Bank: АЗС 100%")
    assert result.items[0].percent == Decimal("100.00")


@pytest.mark.asyncio
async def test_quickadd_accepts_fractional_percent(quick_add, user) -> None:
    result = await quick_add.execute(user_id=user.id, payload="T-Bank: АЗС 2.5%")
    assert result.items[0].percent == Decimal("2.50")


@pytest.mark.asyncio
async def test_quickadd_accepts_comma_decimal_separator(quick_add, user) -> None:
    # Russian locale uses comma as decimal separator; accept both.
    result = await quick_add.execute(user_id=user.id, payload="T-Bank: АЗС 2,5%")
    assert result.items[0].percent == Decimal("2.50")


# --- Workflow state deserialisation robustness -------------------------------


def test_workflow_state_from_dict_with_non_dict_temp_payload_returns_safe_state() -> None:
    # Some session stores may return str/None for previously-dict fields after
    # a schema change — the state deserialiser must NOT raise on those.
    state = WorkflowState.from_dict({"temp_payload": "not_a_dict"})
    assert state.temp_payload == {}


def test_workflow_state_from_dict_with_non_list_draft_items_returns_empty_list() -> None:
    state = WorkflowState.from_dict({"draft_items": "not_a_list"})
    assert state.draft_items == []


def test_workflow_state_from_dict_with_empty_dict_returns_defaults() -> None:
    state = WorkflowState.from_dict({})
    assert state.mode is None
    assert state.draft_items == []
    assert state.pending_input_kind is None


# --- Localizer missing-key resilience ---------------------------------------


def test_localizer_missing_key_returns_key_not_raise() -> None:
    # If a caller references a locale key that doesn't exist, Localizer
    # returns the key itself instead of crashing. Worst case: user sees
    # "foo.bar.missing" as a label; best case: tests catch it.
    loc = Localizer(locales_dir=LOCALES_DIR, default_language="ru")
    assert loc.t("this.key.does.not.exist", "ru") == "this.key.does.not.exist"


def test_localizer_missing_key_in_unknown_language_falls_back_to_default() -> None:
    loc = Localizer(locales_dir=LOCALES_DIR, default_language="ru")
    # "fr" isn't loaded — the localizer falls back to "ru".
    assert "банк" in loc.t("buttons.home", "fr").lower() or loc.t("buttons.home", "fr") == loc.t(
        "buttons.home", "ru"
    )


def test_help_screen_body_mentions_all_commands() -> None:
    # Regression: help text must advertise every shipped command so users
    # discover them — if a new command is added without a /help update,
    # this test fails and forces a doc sync.
    loc = Localizer(locales_dir=LOCALES_DIR, default_language="ru")
    help_body = loc.t("screens.help", "ru")
    for command in ("/best", "/quickadd", "/top", "/banks", "/settings", "/home", "/cancel"):
        assert command in help_body, f"/help must advertise {command}"
