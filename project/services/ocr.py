"""OCR service supporting normal and smart modes."""
from __future__ import annotations

from typing import List


class OCRService:
    def __init__(self) -> None:
        self.mode = "smart"

    def set_mode(self, mode: str) -> None:
        if mode not in {"basic", "smart"}:
            raise ValueError("Unsupported OCR mode")
        self.mode = mode

    def extract_lines(self, image_bytes: bytes) -> List[str]:
        if not image_bytes:
            return []
        payload = image_bytes.decode("utf-8", errors="ignore")
        lines = [line.strip() for line in payload.splitlines() if line.strip()]
        if self.mode == "smart":
            return [line for line in lines if any(char.isdigit() for char in line)]
        return lines
