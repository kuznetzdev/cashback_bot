from __future__ import annotations

from app.domain.models import BankScore, CashbackDraftItem, CategoryLeader, UserLogEntry
from app.domain.services.categories import CategoryService


def format_items_lines(items: list[CashbackDraftItem], categories: CategoryService, language: str) -> str:
    if not items:
        return "-"
    return "\n".join(
        f"- {categories.display_name(item.normalized_category, language)} / {item.raw_category}: {item.percent}%"
        for item in items
    )


def format_history_entries(logs: list[UserLogEntry]) -> str:
    return "\n".join(f"- {entry.created_at.isoformat(timespec='minutes')} {entry.action}" for entry in logs)


def format_ranking(leaders: list[CategoryLeader], global_rating: list[BankScore]) -> tuple[str, str]:
    leaders_text = "\n".join(
        f"- {item.category_name}: {item.best_percent}% ({', '.join(item.bank_names)})" for item in leaders
    )
    global_text = "\n".join(f"- {item.bank_name}: {item.score}" for item in global_rating)
    return leaders_text, global_text


def target_label(target_name: str) -> str:
    labels = {
        "open_home": "labels.target_home",
        "open_help": "labels.target_help",
        "open_add_bank": "labels.target_add_bank",
        "open_my_banks": "labels.target_my_banks",
        "open_top": "labels.target_top",
        "open_settings": "labels.target_settings",
        "open_history": "labels.target_history",
        "cancel_flow": "labels.target_cancel",
        "start": "labels.target_home",
    }
    return labels.get(target_name, "labels.target_other")
