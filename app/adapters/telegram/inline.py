from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

from app.adapters.telegram.deep_links import PAYLOAD_INLINE, PAYLOAD_INLINE_SETUP
from app.application import ApplicationFacade
from app.application.use_cases.ranking_snapshot import RankingSnapshot
from app.domain.models import CategoryLeader, UserAccount
from app.i18n.localizer import Localizer

logger = logging.getLogger(__name__)


_MAX_RESULTS = 10
_TOP_CATEGORIES_FALLBACK = 5

_RESULT_ID_ONBOARDING = "onboarding"
_RESULT_ID_EMPTY_BANKS = "empty_banks"
_RESULT_PREFIX_MATCH = "match"
_RESULT_PREFIX_TOP = "top"
_RESULT_PREFIX_NO_MATCH = "nomatch"


@dataclass(slots=True)
class InlineDependencies:
    facade: ApplicationFacade
    localizer: Localizer
    default_language: str
    bot_username: str | None


async def handle_inline_query(query: InlineQuery, deps: InlineDependencies) -> None:
    """Answer a Telegram inline query with the user's best card for the query
    category. Falls back to the user's top-5 categories when the query is
    empty or doesn't match. Returns a single "open the bot" result when the
    user has never started the bot — never silently creates accounts.

    Any facade-level error (DB outage, timeout) is swallowed and surfaced as
    an empty inline response — Telegram shows "no results" rather than
    hanging or exposing an exception. The error is logged for ops."""

    if query.from_user is None:
        await _answer(query, [], deps, cache_time=5)
        return

    try:
        user = await deps.facade.find_user_by_external_identity(
            provider="telegram",
            provider_user_id=str(query.from_user.id),
        )
        if user is None:
            await _answer(query, [_onboarding_result(deps)], deps, switch_pm=True, cache_time=5)
            return

        raw_query = (query.query or "").strip()
        snapshot = await deps.facade.ranking_snapshot(
            user_id=user.id, query=raw_query, language=user.language
        )
    except Exception as error:
        # Any downstream failure (DB unavailable, facade exception) should not
        # surface as a hung inline query. Return empty so Telegram shows "no
        # results" and the user can retry / message the bot directly.
        logger.warning("Inline query failed during facade call: %s", error)
        await _answer(query, [], deps, cache_time=5)
        return

    if not snapshot.leaders:
        await _answer(query, [_empty_banks_result(user, deps)], deps, switch_pm=True, cache_time=0)
        return

    results = _build_results(snapshot, user, deps)
    await _answer(query, results[:_MAX_RESULTS], deps, cache_time=0)


def _build_results(
    snapshot: RankingSnapshot,
    user: UserAccount,
    deps: InlineDependencies,
) -> list[InlineQueryResultArticle]:
    results: list[InlineQueryResultArticle] = []
    if snapshot.query:
        if snapshot.best_match is not None:
            results.append(
                _leader_article(
                    snapshot.best_match,
                    user,
                    deps,
                    result_id=_stable_id(_RESULT_PREFIX_MATCH, snapshot.query, snapshot.normalized_slug),
                )
            )
        else:
            results.append(_no_match_result(snapshot.query, user, deps))

    fallback_count = _TOP_CATEGORIES_FALLBACK if snapshot.query else _MAX_RESULTS
    for leader in snapshot.leaders[:fallback_count]:
        results.append(
            _leader_article(
                leader,
                user,
                deps,
                result_id=_stable_id(_RESULT_PREFIX_TOP, leader.category_slug),
            )
        )
    return results


async def _answer(
    query: InlineQuery,
    results: list[InlineQueryResultArticle],
    deps: InlineDependencies,
    *,
    cache_time: int = 0,
    switch_pm: bool = False,
) -> None:
    kwargs: dict[str, object] = {
        "results": results,
        "cache_time": cache_time,
        "is_personal": True,
    }
    if switch_pm:
        language = deps.default_language
        kwargs["switch_pm_text"] = deps.localizer.t("inline.open_bot", language)
        kwargs["switch_pm_parameter"] = PAYLOAD_INLINE
    try:
        await query.answer(**kwargs)
    except Exception as error:  # pragma: no cover - best-effort logging
        logger.warning("Failed to answer inline query: %s", error)


def _leader_article(
    leader: CategoryLeader,
    user: UserAccount,
    deps: InlineDependencies,
    *,
    result_id: str,
) -> InlineQueryResultArticle:
    params = {
        "category": leader.category_name,
        "percent": _format_percent(leader.best_percent),
        "banks": _format_bank_list(leader.bank_names, user.language, deps),
    }
    return _build_article(
        result_id=result_id,
        title=deps.localizer.t("inline.result_title", user.language, params),
        description=deps.localizer.t("inline.result_description", user.language, params),
        message_text=deps.localizer.t("inline.share_message", user.language, params),
    )


def _no_match_result(
    raw_query: str,
    user: UserAccount,
    deps: InlineDependencies,
) -> InlineQueryResultArticle:
    params = {"query": raw_query}
    return _build_article(
        result_id=_stable_id(_RESULT_PREFIX_NO_MATCH, raw_query),
        title=deps.localizer.t("inline.no_match_title", user.language, params),
        description=deps.localizer.t("inline.no_match_description", user.language),
        message_text=deps.localizer.t("inline.no_match_body", user.language, params),
    )


def _onboarding_result(deps: InlineDependencies) -> InlineQueryResultArticle:
    language = deps.default_language
    link = _deep_link(deps.bot_username, payload=PAYLOAD_INLINE)
    return _build_article(
        result_id=_RESULT_ID_ONBOARDING,
        title=deps.localizer.t("inline.onboarding_title", language),
        description=deps.localizer.t("inline.onboarding_description", language),
        message_text=deps.localizer.t(
            "inline.onboarding_body",
            language,
            {"link": link} if link else None,
        ),
    )


def _empty_banks_result(user: UserAccount, deps: InlineDependencies) -> InlineQueryResultArticle:
    link = _deep_link(deps.bot_username, payload=PAYLOAD_INLINE_SETUP)
    return _build_article(
        result_id=_RESULT_ID_EMPTY_BANKS,
        title=deps.localizer.t("inline.empty_banks_title", user.language),
        description=deps.localizer.t("inline.empty_banks_description", user.language),
        message_text=deps.localizer.t(
            "inline.empty_banks_body",
            user.language,
            {"link": link} if link else None,
        ),
    )


def _build_article(
    *,
    result_id: str,
    title: str,
    description: str,
    message_text: str,
) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=result_id,
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(message_text=message_text),
    )


def _format_percent(percent) -> str:
    return f"{percent:g}" if hasattr(percent, "__float__") else str(percent)


def _format_bank_list(bank_names: list[str], language: str, deps: InlineDependencies) -> str:
    if not bank_names:
        return deps.localizer.t("inline.no_banks_placeholder", language)
    return ", ".join(bank_names)


def _deep_link(bot_username: str | None, *, payload: str) -> str | None:
    if not bot_username:
        return None
    return f"https://t.me/{bot_username}?start={payload}"


def _stable_id(*parts: str) -> str:
    # Telegram requires result IDs ≤ 64 chars; hashing gives a stable short id
    # regardless of unicode query text.
    joined = "|".join(parts)
    return hashlib.sha1(joined.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
