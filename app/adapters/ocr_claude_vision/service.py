from __future__ import annotations

import asyncio
import base64
import logging
from io import BytesIO

from anthropic import APIError, AsyncAnthropic, BadRequestError
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.adapters._shared import validate_image_upload
from app.application.contracts.ports import OCRPort
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are an extraction engine for Russian and English bank-app screenshots. "
    "Given an image of a bank's cashback list (categories and percent values), "
    "return ONLY the concrete cashback offers shown for the CURRENT active period. "
    "Ignore promotional headers, navigation chrome, account balances, transaction "
    "history, and any categories that are merely offered for selection but not "
    "currently active. Preserve category names exactly as they appear in the image "
    "(Russian → Russian, English → English). Report percent as a number between "
    "0 and 100 (strip the '%' sign). If the same category appears multiple times, "
    "keep only the highest percent."
)

USER_INSTRUCTION = (
    "Extract every active cashback offer from this screenshot. Return strictly "
    "in the structured schema — no commentary, no extra fields."
)


class _CashbackOffer(BaseModel):
    category: str = Field(description="Category name exactly as shown on the screenshot.")
    percent: float = Field(ge=0, le=100, description="Cashback percent, 0-100.")


class _CashbackExtraction(BaseModel):
    offers: list[_CashbackOffer] = Field(default_factory=list)


class ClaudeVisionOCRAdapter(OCRPort):
    """OCR adapter that uses Claude's vision + structured outputs to parse
    bank-app screenshots end-to-end.

    Returns the same ``Category: N%`` per-line format as Tesseract so
    ``ParserService`` stays unchanged; internally one ``messages.parse`` call
    fills a typed ``offers`` list, which is then serialized for the parser.
    """

    _SUPPORTED_MEDIA = {
        "image/png": "image/png",
        "image/jpg": "image/jpeg",
        "image/jpeg": "image/jpeg",
        "image/gif": "image/gif",
        "image/webp": "image/webp",
    }

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-opus-4-7",
        timeout: int = 60,
        max_file_size: int = 5 * 1024 * 1024,
        max_tokens: int = 4096,
    ) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for ClaudeVisionOCRAdapter")

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._timeout = timeout
        self._max_file_size = max_file_size
        self._max_tokens = max_tokens

    async def extract_text(self, upload: ImageUpload) -> str:
        validate_image_upload(upload, max_file_size=self._max_file_size)

        loop = asyncio.get_running_loop()
        try:
            media_type, image_b64 = await loop.run_in_executor(None, self._prepare_image, upload)
        except ValidationError:
            raise
        except (UnidentifiedImageError, OSError, TypeError, ValueError) as error:
            raise ValidationError("errors.broken_image") from error

        try:
            extraction = await asyncio.wait_for(
                self._call_claude(image_b64, media_type),
                timeout=self._timeout,
            )
        except TimeoutError as error:
            raise ValidationError("errors.ocr_timeout") from error
        except BadRequestError as error:
            logger.warning("Claude Vision rejected the screenshot: %s", error)
            raise ValidationError("errors.broken_image") from error
        except APIError as error:
            logger.warning("Claude Vision API error: %s", error)
            raise ValidationError("errors.ocr_timeout") from error

        offers = self._deduplicate(extraction.offers)
        if not offers:
            raise ValidationError("errors.ocr_empty")
        return "\n".join(f"{offer.category}: {offer.percent:g}%" for offer in offers)

    async def _call_claude(self, image_b64: str, media_type: str) -> _CashbackExtraction:
        response = await self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            output_format=_CashbackExtraction,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": USER_INSTRUCTION},
                    ],
                }
            ],
        )
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise ValidationError("errors.ocr_empty")
        return parsed

    def _prepare_image(self, upload: ImageUpload) -> tuple[str, str]:
        media_type = self._detect_media_type(upload)
        image_b64 = base64.standard_b64encode(upload.content).decode("ascii")
        return media_type, image_b64

    def _detect_media_type(self, upload: ImageUpload) -> str:
        declared = (upload.content_type or "").lower().split(";", 1)[0].strip()
        if declared in self._SUPPORTED_MEDIA:
            return self._SUPPORTED_MEDIA[declared]
        with Image.open(BytesIO(upload.content)) as image:
            fmt = (image.format or "").lower()
        return self._SUPPORTED_MEDIA.get(f"image/{fmt}", "image/png")

    @staticmethod
    def _deduplicate(offers: list[_CashbackOffer]) -> list[_CashbackOffer]:
        best: dict[str, _CashbackOffer] = {}
        for offer in offers:
            category = offer.category.strip()
            if not category or offer.percent <= 0 or offer.percent > 100:
                continue
            key = category.casefold()
            current = best.get(key)
            if current is None or offer.percent > current.percent:
                best[key] = _CashbackOffer(category=category, percent=offer.percent)
        return sorted(best.values(), key=lambda item: (-item.percent, item.category.casefold()))
