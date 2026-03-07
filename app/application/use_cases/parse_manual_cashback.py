from __future__ import annotations

from app.domain.models import CashbackDraftItem
from app.domain.services.parsing import ParserService


class ParseManualCashbackUseCase:
    def __init__(self, parser: ParserService) -> None:
        self.parser = parser

    def execute(self, text: str) -> list[CashbackDraftItem]:
        return self.parser.parse_manual_lines(text)
