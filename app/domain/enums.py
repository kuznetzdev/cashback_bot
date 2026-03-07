from __future__ import annotations

from enum import Enum


class Language(str, Enum):
    RU = "ru"
    EN = "en"


class SourceType(str, Enum):
    OCR = "ocr"
    MANUAL = "manual"
    TEMPLATE = "template"
