from __future__ import annotations

from app.application.use_cases.process_uploaded_image import ProcessUploadedImageUseCase


class ProcessCashbackImageUseCase(ProcessUploadedImageUseCase):
    """Compatibility wrapper for the renamed upload-processing use case."""
