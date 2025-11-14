"""In-memory persistence layer used by the bot services."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Template:
    template_id: str
    name: str
    fields: Dict[str, str]


@dataclass
class Bank:
    bank_id: str
    name: str
    product: str
    templates: List[Template] = field(default_factory=list)


@dataclass
class Transaction:
    transaction_id: str
    bank_id: str
    amount: float
    category: str
    description: str


@dataclass
class Recommendation:
    recommendation_id: str
    text: str


@dataclass
class NotificationSettings:
    mode: str
    hour: int = 9


@dataclass
class HistoryEntry:
    entry_id: str
    summary: str


@dataclass
class Achievement:
    code: str
    title: str
    progress: int


@dataclass
class BankWizardState:
    step: int
    name: Optional[str] = None
    product: Optional[str] = None


@dataclass
class UserProfile:
    user_id: int
    banks: Dict[str, Bank] = field(default_factory=dict)
    transactions: List[Transaction] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)
    history: List[HistoryEntry] = field(default_factory=list)
    achievements: List[Achievement] = field(default_factory=list)
    templates: Dict[str, Template] = field(default_factory=dict)
    notifications: NotificationSettings = field(default_factory=lambda: NotificationSettings(mode="daily"))
    wizard_state: Optional[BankWizardState] = None


class InMemoryDB:
    """Simple in-memory data store safe for tests."""

    def __init__(self) -> None:
        self._profiles: Dict[int, UserProfile] = {}

    def _profile(self, user_id: int) -> UserProfile:
        if user_id not in self._profiles:
            self._profiles[user_id] = UserProfile(user_id=user_id)
        return self._profiles[user_id]

    # Bank operations -----------------------------------------------------

    def start_bank_wizard(self, user_id: int) -> BankWizardState:
        profile = self._profile(user_id)
        profile.wizard_state = BankWizardState(step=0)
        return profile.wizard_state

    def update_bank_wizard(self, user_id: int, name: Optional[str] = None, product: Optional[str] = None) -> BankWizardState:
        profile = self._profile(user_id)
        if profile.wizard_state is None:
            profile.wizard_state = BankWizardState(step=0)
        if name is not None:
            profile.wizard_state.name = name
            profile.wizard_state.step = 1
        if product is not None:
            profile.wizard_state.product = product
            profile.wizard_state.step = 2
        return profile.wizard_state

    def complete_bank_wizard(self, user_id: int, bank_id: str) -> Bank:
        profile = self._profile(user_id)
        state = profile.wizard_state
        if state is None or state.name is None or state.product is None:
            raise ValueError("Wizard is not ready to complete")
        bank = Bank(bank_id=bank_id, name=state.name, product=state.product)
        profile.banks[bank_id] = bank
        profile.wizard_state = None
        return bank

    # Template operations -------------------------------------------------

    def add_template(self, user_id: int, template: Template) -> None:
        self._profile(user_id).templates[template.template_id] = template

    def delete_template(self, user_id: int, template_id: str) -> None:
        self._profile(user_id).templates.pop(template_id, None)

    # Transaction operations ----------------------------------------------

    def add_transaction(self, user_id: int, transaction: Transaction) -> None:
        self._profile(user_id).transactions.append(transaction)

    def list_transactions(self, user_id: int) -> List[Transaction]:
        return list(self._profile(user_id).transactions)

    # Recommendation operations ------------------------------------------

    def set_recommendations(self, user_id: int, recommendations: List[Recommendation]) -> None:
        self._profile(user_id).recommendations = recommendations

    def list_recommendations(self, user_id: int) -> List[Recommendation]:
        return list(self._profile(user_id).recommendations)

    # History operations --------------------------------------------------

    def add_history_entry(self, user_id: int, entry: HistoryEntry) -> None:
        self._profile(user_id).history.append(entry)

    def list_history(self, user_id: int) -> List[HistoryEntry]:
        return list(self._profile(user_id).history)

    # Achievement operations ---------------------------------------------

    def set_achievements(self, user_id: int, achievements: List[Achievement]) -> None:
        self._profile(user_id).achievements = achievements

    def list_achievements(self, user_id: int) -> List[Achievement]:
        return list(self._profile(user_id).achievements)

    # Notification settings ----------------------------------------------

    def update_notifications(self, user_id: int, mode: str, hour: int) -> NotificationSettings:
        profile = self._profile(user_id)
        profile.notifications = NotificationSettings(mode=mode, hour=hour)
        return profile.notifications

    def get_notifications(self, user_id: int) -> NotificationSettings:
        return self._profile(user_id).notifications

    # Misc ----------------------------------------------------------------

    def reset(self) -> None:
        self._profiles.clear()
