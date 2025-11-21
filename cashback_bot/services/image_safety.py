from __future__ import annotations

"""Validates uploaded images before OCR."""
from dataclasses import dataclass


@dataclass
class ImageSafetyReport:
    ok: bool
    reason: str | None = None


class ImageSafetyService:
    MIN_SIZE = 1024  # bytes
    MAX_SIZE = 8 * 1024 * 1024

    def validate(self, image_bytes: bytes) -> ImageSafetyReport:
        size = len(image_bytes)
        if size < self.MIN_SIZE:
            return ImageSafetyReport(False, "too_small")
        if size > self.MAX_SIZE:
            return ImageSafetyReport(False, "too_large")
        return ImageSafetyReport(True, None)
