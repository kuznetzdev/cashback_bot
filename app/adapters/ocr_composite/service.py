from __future__ import annotations

import logging
from collections.abc import Callable

from app.application.contracts.ports import OCRPort
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError

logger = logging.getLogger(__name__)


# Errors that mean "the primary engine couldn't produce a useful extraction"
# and where retrying with a more powerful backend may still succeed. Broken
# images and oversized files are NOT on this list — they will fail equally on
# any engine, and we don't want to spend money on a second doomed attempt.
_ESCALATABLE_ERROR_KEYS = frozenset({"errors.ocr_empty", "errors.ocr_timeout"})


class CompositeOCRAdapter(OCRPort):
    """Two-tier OCR: run a cheap primary engine (Tesseract) first, fall back to
    a more expensive one (Claude/OpenAI vision) only when the primary can't
    extract anything useful. This keeps the AI bill small while still giving
    the user a second chance on the hard screenshots Tesseract mangles.

    Deterministic user-input errors (file too large, broken image) are NOT
    escalated — they would fail on both engines and we don't want to pay for
    the round-trip. Only empty/timeout results trigger the error-based fallback.

    Additionally, when ``content_validator`` is supplied, it is invoked on the
    primary engine's successful output. A validator that returns ``False``
    means "the text came back syntactically fine but contains no usable
    cashback offers" — Tesseract does this on compressed / stylised bank
    screens where it sees shapes but can't read them. In that case we still
    escalate to the fallback so the user has the best possible shot.
    """

    def __init__(
        self,
        primary: OCRPort,
        fallback: OCRPort | None = None,
        *,
        content_validator: Callable[[str], bool] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._content_validator = content_validator

    async def extract_text(self, upload: ImageUpload) -> str:
        try:
            primary_text = await self._primary.extract_text(upload)
        except ValidationError as primary_error:
            if self._fallback is None or primary_error.message_key not in _ESCALATABLE_ERROR_KEYS:
                raise
            logger.info(
                "Primary OCR returned %s; escalating to fallback adapter.",
                primary_error.message_key,
            )
            return await self._escalate_to_fallback(upload)

        if self._content_validator is not None and not self._content_validator(primary_text):
            if self._fallback is None:
                # No escalation path — return what we got and let the caller
                # decide. Parser will raise errors.ocr_empty downstream.
                return primary_text
            logger.info("Primary OCR text had no parseable cashback offers; escalating to fallback.")
            try:
                return await self._escalate_to_fallback(upload)
            except ValidationError as fallback_error:
                # Fallback also produced nothing useful. Prefer the fallback's
                # error key (it's the engine the user effectively asked for).
                logger.info(
                    "Fallback OCR after content-validator miss also failed: %s",
                    fallback_error.message_key,
                )
                raise

        return primary_text

    async def _escalate_to_fallback(self, upload: ImageUpload) -> str:
        assert self._fallback is not None
        try:
            result = await self._fallback.extract_text(upload)
        except ValidationError as fallback_error:
            logger.info(
                "Fallback OCR also failed with %s; surfacing the fallback error.",
                fallback_error.message_key,
            )
            raise
        logger.info("Fallback OCR rescued the request.")
        return result
