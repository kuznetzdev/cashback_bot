"""Instrumentation wrapper for OCR adapters.

Wraps any :class:`OCRPort` implementation and records the call outcome into
a Prometheus-style counter. Keeps the OCR adapters themselves free of
metrics concerns — they stay focused on "image bytes in, text out".

The counter call site tolerates both real Prometheus counters (with
``.labels(...).inc()``) and anything that quacks the same way, so tests
can stub it with a ``MagicMock`` without importing prometheus_client.
"""
from __future__ import annotations

import logging
from typing import Any

from app.application.contracts.ports import OCRPort
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError

logger = logging.getLogger(__name__)


class MetricsOCRAdapter(OCRPort):
    """Wraps ``inner`` and increments a labelled counter on each call.

    Labels used:

    * ``provider`` — static, passed at construction time (e.g. ``"tesseract"``,
      ``"openai"``, ``"composite"``).
    * ``result``   — one of ``"ok"``, ``"empty"`` (the adapter raised
      ``errors.ocr_empty``), ``"timeout"`` (``errors.ocr_timeout``), or
      ``"error"`` (any other ``ValidationError`` / exception).
    """

    def __init__(
        self,
        inner: OCRPort,
        *,
        provider: str,
        counter: Any,
    ) -> None:
        self._inner = inner
        self._provider = provider
        self._counter = counter

    async def extract_text(self, upload: ImageUpload) -> str:
        try:
            text = await self._inner.extract_text(upload)
        except ValidationError as error:
            result = _result_from_error_key(error.message_key)
            self._record(result)
            raise
        except Exception:
            # Unhandled exceptions still count as errors — don't let the
            # counter silently drop them, but preserve the traceback.
            self._record("error")
            raise
        else:
            self._record("empty" if not text.strip() else "ok")
            return text

    # ------------------------------------------------------------------
    # Delegation for adapters that expose cleanup hooks (composite
    # adapter's runtime.py walks ``_primary`` / ``_fallback``).
    # ------------------------------------------------------------------
    @property
    def _primary(self):  # pragma: no cover - trivial
        return getattr(self._inner, "_primary", None)

    @property
    def _fallback(self):  # pragma: no cover - trivial
        return getattr(self._inner, "_fallback", None)

    async def close(self) -> None:  # pragma: no cover - trivial
        closer = getattr(self._inner, "close", None)
        if callable(closer):
            result = closer()
            if hasattr(result, "__await__"):
                await result  # type: ignore[func-returns-value]

    def _record(self, result: str) -> None:
        try:
            self._counter.labels(provider=self._provider, result=result).inc()
        except Exception:  # pragma: no cover - metrics must never break OCR
            logger.debug("Failed to record OCR metric")


def _result_from_error_key(error_key: str) -> str:
    if error_key == "errors.ocr_empty":
        return "empty"
    if error_key == "errors.ocr_timeout":
        return "timeout"
    return "error"
