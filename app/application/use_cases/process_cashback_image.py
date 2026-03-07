from __future__ import annotations

from pathlib import Path

from app.application.contracts.ports import OCRPort
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem
from app.domain.services.parsing import ParserService


class ProcessCashbackImageUseCase:
    def __init__(self, ocr: OCRPort, parser: ParserService) -> None:
        self.ocr = ocr
        self.parser = parser

    async def execute(self, path: Path) -> list[CashbackDraftItem]:
        text = await self.ocr.extract_text(path)
        items = self.parser.parse_ocr_text(text)
        if not items:
            raise ValidationError("errors.ocr_empty")
        return items
