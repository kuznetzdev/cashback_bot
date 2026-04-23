from __future__ import annotations

import logging

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
    the round-trip. Only empty/timeout results trigger the fallback.
    """

    def __init__(self, primary: OCRPort, fallback: OCRPort | None = None) -> None:
        self._primary = primary
        self._fallback = fallback

    async def extract_text(self, upload: ImageUpload) -> str:
        try:
            return await self._primary.extract_text(upload)
        except ValidationError as primary_error:
            if self._fallback is None or primary_error.message_key not in _ESCALATABLE_ERROR_KEYS:
                raise
            logger.info(
                "Primary OCR returned %s; escalating to fallback adapter.",
                primary_error.message_key,
            )
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
