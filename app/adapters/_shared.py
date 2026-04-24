from __future__ import annotations

from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError


def validate_image_upload(upload: ImageUpload, *, max_file_size: int) -> None:
    """Guard used by every OCR adapter before touching the image bytes."""
    if not upload.content:
        raise ValidationError("errors.broken_image")
    if len(upload.content) > max_file_size:
        raise ValidationError("errors.file_too_large")
