from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        message_key: str,
        *,
        log_action: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message_key)
        self.message_key = message_key
        self.log_action = log_action
        self.payload = payload or {}


class ValidationError(AppError):
    pass


class FileTooLargeError(ValidationError):
    def __init__(self, max_size: int) -> None:
        super().__init__("errors.file_too_large", payload={"max_size": max_size})


class UnsupportedFileError(ValidationError):
    def __init__(self) -> None:
        super().__init__("errors.unsupported_file")


class OCRTimeoutError(AppError):
    def __init__(self) -> None:
        super().__init__("errors.ocr_timeout", log_action="ocr_timeout")


class OCREmptyError(AppError):
    def __init__(self) -> None:
        super().__init__("errors.ocr_empty", log_action="ocr_empty")


class ImageProcessingError(AppError):
    def __init__(self) -> None:
        super().__init__("errors.broken_image", log_action="ocr_invalid_image")


class NotFoundError(AppError):
    pass


class DatabaseOperationError(AppError):
    def __init__(self) -> None:
        super().__init__("errors.database", log_action="database_error")
