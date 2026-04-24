"""Correlation id plumbing shared by telegram middleware, web middleware and
structlog so a single update / HTTP request can be traced end-to-end."""
from __future__ import annotations

from contextvars import ContextVar

# Short (~8 char) id set by the request-entry middleware and read by every
# structlog/logging call during the same update. Empty string means "no
# correlation id set" — structlog omits the field rather than renders blank.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    return correlation_id_var.get() or ""


def set_correlation_id(value: str):  # noqa: ANN201 - returns the reset token
    return correlation_id_var.set(value)
