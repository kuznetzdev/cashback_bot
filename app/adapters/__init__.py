"""Adapters layer."""

from app.adapters.ocr_tesseract import TesseractOCRAdapter
from app.adapters.scheduler import ReminderLoop
from app.adapters.system import NoopReminderSender, SystemClock

__all__ = [
    "TesseractOCRAdapter",
    "ReminderLoop",
    "SystemClock",
    "NoopReminderSender",
]
