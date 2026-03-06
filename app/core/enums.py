from enum import Enum


class Language(str, Enum):
    RU = "ru"
    EN = "en"


class SourceType(str, Enum):
    OCR = "ocr"
    MANUAL = "manual"
    TEMPLATE = "template"


class DraftMode(str, Enum):
    CREATE = "create"
    EDIT = "edit"
