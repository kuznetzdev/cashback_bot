from __future__ import annotations


class DomainError(Exception):
    def __init__(self, message_key: str, payload: dict[str, object] | None = None) -> None:
        super().__init__(message_key)
        self.message_key = message_key
        self.payload = payload or {}


class ValidationError(DomainError):
    pass


class NotFoundError(DomainError):
    pass
