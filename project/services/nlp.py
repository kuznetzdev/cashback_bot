"""NLP helpers for cashback receipt processing."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from .categories import CategoryNormalizer

LOGGER = logging.getLogger(__name__)

DELETE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"delete last",
        r"удал(и|ить) последн",
        r"remove receipt",
    )
]

BEST_CASHBACK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"best cashback",
        r"лучший кешбек",
        r"top rewards",
    )
]

RECOMMEND_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"recommend",
        r"рекомендац",
    )
]

HISTORY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"history",
        r"журнал",
    )
]

PROFILE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"profile",
        r"профиль",
    )
]


@dataclass(frozen=True)
class ParsedReceipt:
    merchant: str
    category: str
    amount: float
    cashback: float
    currency: str
    purchase_date: str


class NLPService:
    """Simple rule-based NLP component for the bot."""

    def __init__(self, normalizer: CategoryNormalizer) -> None:
        self._normalizer = normalizer

    def detect_intent(self, text: str) -> Optional[str]:
        for pattern in DELETE_PATTERNS:
            if pattern.search(text):
                return "delete_last"
        for pattern in BEST_CASHBACK_PATTERNS:
            if pattern.search(text):
                return "best_cashback"
        for pattern in RECOMMEND_PATTERNS:
            if pattern.search(text):
                return "recommendations"
        for pattern in HISTORY_PATTERNS:
            if pattern.search(text):
                return "history"
        for pattern in PROFILE_PATTERNS:
            if pattern.search(text):
                return "profile"
        return None

    def parse_receipt(self, text: str) -> Optional[ParsedReceipt]:
        LOGGER.debug("Parsing receipt text: %s", text)
        amount_match = re.search(r"([0-9]+(?:[.,][0-9]{1,2})?)\s*(RUB|USD|EUR|₽|\$|€)", text, re.IGNORECASE)
        if not amount_match:
            LOGGER.info("Unable to locate amount in receipt text")
            return None

        raw_amount = amount_match.group(1).replace(",", ".")
        currency_symbol = amount_match.group(2).upper()
        currency = {
            "₽": "RUB",
            "$": "USD",
            "€": "EUR",
        }.get(currency_symbol, currency_symbol)

        merchant_match = re.search(r"merchant[:\s]+([\w\s&'-]+)", text, re.IGNORECASE)
        merchant = merchant_match.group(1).strip() if merchant_match else "Unknown"

        category_match = re.search(r"category[:\s]+([\w\s&'-]+)", text, re.IGNORECASE)
        category = category_match.group(1).strip() if category_match else "general"
        normalized_category = self._normalizer.normalize(category)

        cashback_match = re.search(r"cashback[:\s]+([0-9]+(?:[.,][0-9]{1,2})?)", text, re.IGNORECASE)
        cashback = float(cashback_match.group(1).replace(",", ".")) if cashback_match else 0.0

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        purchase_date = date_match.group(1) if date_match else ""

        return ParsedReceipt(
            merchant=merchant,
            category=normalized_category,
            amount=float(raw_amount),
            cashback=cashback,
            currency=currency,
            purchase_date=purchase_date or "",
        )

    def normalize_category(self, category: str) -> str:
        return self._normalizer.normalize(category)

    def parse_category_block(self, text: str) -> List[tuple[str, float]]:
        results: List[tuple[str, float]] = []
        for line in text.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            match = re.search(r"(.+?)[\s:=\-]+([0-9]+(?:[.,][0-9]{1,2})?)%?", cleaned)
            if not match:
                continue
            name = match.group(1).strip()
            rate = float(match.group(2).replace(",", ".")) / 100
            results.append((self._normalizer.normalize(name), rate))
        return results
