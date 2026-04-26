from __future__ import annotations

from enum import StrEnum


class Language(StrEnum):
    RU = "ru"
    EN = "en"


class SourceType(StrEnum):
    OCR = "ocr"
    MANUAL = "manual"
    TEMPLATE = "template"


class OCRProvider(StrEnum):
    AUTO = "auto"
    OPENAI = "openai"
    TESSERACT = "tesseract"
