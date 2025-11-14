"""In-memory persistence layer for the cashback bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Bank:
    identifier: str
    name: str
    accounts: List[str] = field(default_factory=list)
    preferences: Dict[str, str] = field(default_factory=dict)


@dataclass
class Template:
    identifier: str
    name: str
    pattern: str
    bank_id: Optional[str] = None


@dataclass
class Transaction:
    identifier: str
    amount: float
    category: str
    bank_id: str


@dataclass
class NotificationSettings:
    mode: str = "smart"
    quiet_hours: Optional[str] = None


@dataclass
class GamificationState:
    level: int = 1
    experience: int = 0


@dataclass
class ChatState:
    banks: Dict[str, Bank] = field(default_factory=dict)
    templates: Dict[str, Template] = field(default_factory=dict)
    transactions: List[Transaction] = field(default_factory=list)
    notification_settings: NotificationSettings = field(default_factory=NotificationSettings)
    gamification: GamificationState = field(default_factory=GamificationState)
    log: List[str] = field(default_factory=list)


class Database:
    """Stores all chat specific information."""

    def __init__(self) -> None:
        self._chats: Dict[int, ChatState] = {}

    def _get_chat(self, chat_id: int) -> ChatState:
        if chat_id not in self._chats:
            self._chats[chat_id] = ChatState()
        return self._chats[chat_id]

    # Bank management -----------------------------------------------------------------
    def add_bank(self, chat_id: int, bank: Bank) -> None:
        state = self._get_chat(chat_id)
        state.banks[bank.identifier] = bank
        state.log.append(f"bank:{bank.identifier}:created")

    def get_bank(self, chat_id: int, bank_id: str) -> Optional[Bank]:
        return self._get_chat(chat_id).banks.get(bank_id)

    def list_banks(self, chat_id: int) -> List[Bank]:
        return list(self._get_chat(chat_id).banks.values())

    # Template management -------------------------------------------------------------
    def add_template(self, chat_id: int, template: Template) -> None:
        state = self._get_chat(chat_id)
        state.templates[template.identifier] = template
        state.log.append(f"template:{template.identifier}:created")

    def list_templates(self, chat_id: int) -> List[Template]:
        return list(self._get_chat(chat_id).templates.values())

    def remove_template(self, chat_id: int, template_id: str) -> None:
        state = self._get_chat(chat_id)
        if template_id in state.templates:
            del state.templates[template_id]
            state.log.append(f"template:{template_id}:deleted")

    # Transactions --------------------------------------------------------------------
    def add_transaction(self, chat_id: int, transaction: Transaction) -> None:
        state = self._get_chat(chat_id)
        state.transactions.append(transaction)
        state.log.append(f"transaction:{transaction.identifier}:added")

    def list_transactions(self, chat_id: int) -> List[Transaction]:
        return list(self._get_chat(chat_id).transactions)

    # Analytics -----------------------------------------------------------------------
    def monthly_cashback(self, chat_id: int) -> float:
        transactions = self._get_chat(chat_id).transactions
        return sum(tx.amount for tx in transactions if tx.amount > 0)

    # Notifications -------------------------------------------------------------------
    def get_notifications(self, chat_id: int) -> NotificationSettings:
        return self._get_chat(chat_id).notification_settings

    def update_notifications(self, chat_id: int, **kwargs: str) -> None:
        state = self._get_chat(chat_id)
        for key, value in kwargs.items():
            if hasattr(state.notification_settings, key):
                setattr(state.notification_settings, key, value)
        state.log.append("notifications:updated")

    # Gamification --------------------------------------------------------------------
    def get_gamification(self, chat_id: int) -> GamificationState:
        return self._get_chat(chat_id).gamification

    def add_experience(self, chat_id: int, experience: int) -> None:
        state = self._get_chat(chat_id)
        state.gamification.experience += experience
        while state.gamification.experience >= 100:
            state.gamification.level += 1
            state.gamification.experience -= 100
        state.log.append("gamification:progress")

    # Audit log -----------------------------------------------------------------------
    def get_log(self, chat_id: int) -> List[str]:
        return list(self._get_chat(chat_id).log)


__all__ = [
    "Database",
    "Bank",
    "Template",
    "Transaction",
    "NotificationSettings",
    "GamificationState",
]
