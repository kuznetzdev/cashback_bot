from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ImageUpload:
    content: bytes
    filename: str
    content_type: str
