from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from io import BytesIO

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.adapters._shared import validate_image_upload
from app.adapters.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.application.contracts.ports import OCRPort
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You extract cashback offers from Russian and English bank-app screenshots "
    "(T-Bank, Sber, VTB, MTS Cashback, Yandex Pay, Alfa, Raiffeisen, Ozon, "
    "plus any other RU/EN bank UI). Respond with ONLY a valid JSON object "
    'matching this exact schema: {"offers": [{"category": string, '
    '"percent": number between 0 and 100}]}.\n'
    "\n"
    "INCLUDE only concrete cashback offers currently active on the screen for "
    "the user's ACTIVE card and ACTIVE month. When the screen shows tabs for "
    "multiple months (Март/Апрель/Май) take only the currently selected/"
    "highlighted/underlined month. When the screen shows tabs for multiple "
    "cards (e.g. 'Дебетовая карта · · 1234', 'Накопительный', 'MTC WEEKEND') "
    "take only the foregrounded card.\n"
    "\n"
    "CATEGORY-SELECTION UI — IMPORTANT: some banks let users pick N of M "
    "possible categories and pay cashback only on the selected ones "
    '("Выбрано 3 из 5", "Выберите до 3 категорий"). On those screens each '
    "tile has a check state — filled blue/green checkmark vs empty circle. "
    "INCLUDE only tiles whose checkbox is filled/checked. The unchecked "
    "tiles are offers the user has NOT opted into and must be excluded.\n"
    "\n"
    "When a tile has BOTH a big main title ('Онлайн-покупки') AND a grey "
    "subtitle/description ('Маркетплейсы и интернет-магазины'), emit only "
    "the main title as the category. Tier labels like 'СУПЕРКЭШБЭК' or "
    "'PREMIUM' are badges — drop them; keep the category and the percent.\n"
    "\n"
    "IGNORE everything that is NOT a concrete active cashback line:\n"
    "- section headers and block titles such as 'Категории в апреле', "
    "'Повышенный кэшбэк', 'Ваш кэшбэк на май', 'Любимые категории', "
    "'Категории кэшбэка', 'Выгода в апреле', 'Выгода у партнёров', "
    "'Выгода в цифрах', 'Кешбэк за покупки', 'Кешбэк в категориях', "
    "'Кешбэк и скидки', 'Ваши N категорий', 'Ваши бонусы', 'Ваши категории', "
    "'Еще больше выгоды', 'Подсказки';\n"
    "- eligibility conditions and loyalty tiers such as 'с МТС Premium', "
    "'со СберПрайм', 'За Серебряный уровень', 'для клиентов', "
    "'с подпиской', 'при оплате на сайте', 'с подпиской \"Нова Плюс\" "
    "+5%';\n"
    "- upsell / promo strips such as 'Больше категорий — больше выгоды', "
    "'Выберите N категорий и получайте кэшбэк каждый месяц', "
    "'Как это работает', 'Больше кэшбэка с подпиской';\n"
    "- spending caps and limits such as 'Кешбэк до 1000 ₽', 'до 500 ₽', "
    "'Максимум кэшбэка в месяц — 5 000 ₽', 'Суперкэшбэк — до 10 000 ₽ в "
    "месяц';\n"
    "- balance counters, accrual timers, accumulated totals such as 'Кешбэк "
    "за май 2 843 ₽', 'Начислится 5 июня', '0 ₽ копится до 18 мая', "
    "'Начисления кешбэка', '744 ₽ кешбэк за всё время', card balances "
    "like '75 320,50 ₽';\n"
    "- progress indicators such as 'Выбрано 3 из 5 категорий', 'До конца "
    "месяца 20 дней', 'Осталось 18 дней', 'Действует с 1 по 30 июня', "
    "'Категории обновятся 1 июля', countdown chips;\n"
    "- app chrome, bottom nav tabs ('Главная', 'Платежи', 'Кэшбэк', "
    "'История', 'Продукты', 'Ещё', 'Чат', 'Профиль'), navigation links, "
    "FAQ helpers ('Подробнее', 'Условия программы лояльности', 'Как это "
    "работает'), maintenance toasts ('Проводим техработы'), status bar "
    "time/notifications, transaction lists;\n"
    "- marketing taglines that look like a category but are not "
    "('Кэшбэк на всё' under a tile is a marketing strap-line, NOT a "
    "separate offer);\n"
    "- categories that are merely OFFERED for selection next month but not "
    "yet active (e.g. tabs 'Май' when 'Апрель' is currently selected).\n"
    "\n"
    "Partner-merchant rates shown as distinct blocks (e.g. 'Спортмастер "
    "кешбэк 10%', 'Tasty Coffee 10%') COUNT as cashback offers — include "
    "them as-is, using the partner name as the category. Taxi sub-tiers "
    "(Комфорт, Комфорт+, Ultima) are separate categories and SHOULD be "
    "included individually with their own percents. A base cashback line "
    "like '1% На все покупки' or '1% за всё' IS a cashback offer and MUST "
    "be included.\n"
    "\n"
    "Preserve category names EXACTLY as shown, including qualifiers ('в "
    "Городе', 'и доставка еды') — the downstream normalizer handles those. "
    "Keep Russian Russian and English English. Report percent as a plain "
    "number between 0 and 100 (strip the '%' sign). If the same category "
    "appears more than once keep only the highest percent. Output nothing "
    "outside the JSON object — no commentary, no markdown fences."
)

USER_INSTRUCTION = (
    "Extract every active cashback offer from this screenshot for the "
    "currently selected card and month. Return valid JSON matching the "
    "schema — no commentary, no markdown."
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class _Offer(BaseModel):
    category: str
    percent: float = Field(ge=0, le=100)


class _Extraction(BaseModel):
    offers: list[_Offer] = Field(default_factory=list)


class OpenAIVisionOCRAdapter(OCRPort):
    """OCR adapter that calls an OpenAI-compatible Chat Completions API with
    vision and a JSON response format to turn bank screenshots into structured
    cashback offers.

    Works against OpenAI itself, Russian OpenAI-compatible gateways
    (ProxyAPI, VSEgpt, …), self-hosted Ollama / LM Studio, and any other
    endpoint that speaks the Chat Completions protocol. Only ``base_url``,
    ``model`` and the API key change.
    """

    _SUPPORTED_MEDIA = {
        "image/png": "image/png",
        "image/jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "image/gif": "image/gif",
        "image/webp": "image/webp",
    }

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
        timeout: int = 60,
        max_file_size: int = 5 * 1024 * 1024,
        max_tokens: int = 1024,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIVisionOCRAdapter")
        # Align the SDK timeout with our asyncio.wait_for so the underlying HTTP
        # request is actually aborted when we give up — otherwise the default
        # 10-minute SDK timeout leaks a zombie request after wait_for fires.
        client_kwargs: dict[str, object] = {"api_key": api_key, "timeout": float(timeout)}
        normalized_base_url = (base_url or "").strip()
        if normalized_base_url:
            client_kwargs["base_url"] = normalized_base_url

        self._client = AsyncOpenAI(**client_kwargs)
        self._model = model
        self._timeout = timeout
        self._max_file_size = max_file_size
        self._max_tokens = max_tokens
        # Trip after 5 consecutive errors and stay open for 60 s. Picked so a
        # transient outage (rate-limit window, brief 5xx burst) costs at most
        # ~5 calls before we stop hammering the upstream — the user's photo
        # uploads still escalate to errors.ocr_unavailable but the OpenAI bill
        # and the upstream rate quota are protected.
        self._breaker = breaker or CircuitBreaker(
            name="openai_vision",
            failure_threshold=5,
            cool_down_seconds=60.0,
        )

    async def close(self) -> None:
        """Release the underlying httpx connection pool. Safe to call twice;
        the OpenAI client handles repeated close() gracefully."""
        try:
            await self._client.close()
        except Exception as error:  # pragma: no cover - best-effort cleanup
            logger.debug("OpenAI client close raised: %s", error)

    async def extract_text(self, upload: ImageUpload) -> str:
        validate_image_upload(upload, max_file_size=self._max_file_size)

        loop = asyncio.get_running_loop()
        try:
            media_type, image_b64 = await loop.run_in_executor(None, self._prepare_image, upload)
        except ValidationError:
            raise
        except (UnidentifiedImageError, OSError, TypeError, ValueError) as error:
            raise ValidationError("errors.broken_image") from error

        data_url = f"data:{media_type};base64,{image_b64}"

        try:
            raw_content = await self._breaker.call(
                lambda: asyncio.wait_for(self._call_model(data_url), timeout=self._timeout)
            )
        except CircuitOpenError as error:
            # Upstream is in a known-bad state; don't waste a call on it.
            # Map to the same key as a network error so the composite adapter
            # treats it the same way — and keep the message in `extra` for
            # ops to grep.
            logger.warning("OpenAI vision skipped: %s", error)
            raise ValidationError("errors.ocr_timeout") from error
        except TimeoutError as error:
            raise ValidationError("errors.ocr_timeout") from error
        except (APITimeoutError, APIConnectionError, RateLimitError) as error:
            logger.warning("OpenAI vision transient error: %s", error)
            raise ValidationError("errors.ocr_timeout") from error
        except BadRequestError as error:
            logger.warning("OpenAI vision rejected the screenshot: %s", error)
            raise ValidationError("errors.broken_image") from error
        except AuthenticationError as error:
            logger.error("OpenAI vision auth failed: %s", error)
            raise ValidationError("errors.ocr_timeout") from error
        except APIError as error:
            logger.warning("OpenAI vision API error: %s", error)
            raise ValidationError("errors.ocr_timeout") from error

        offers = self._deduplicate(self._parse_extraction(raw_content).offers)
        if not offers:
            raise ValidationError("errors.ocr_empty")
        return "\n".join(f"{offer.category}: {offer.percent:g}%" for offer in offers)

    async def _call_model(self, data_url: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_INSTRUCTION},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "high"},
                        },
                    ],
                },
            ],
        )
        if not getattr(response, "choices", None):
            return ""
        return (response.choices[0].message.content or "").strip()

    @staticmethod
    def _parse_extraction(raw: str) -> _Extraction:
        payload_text = _FENCE_RE.sub("", (raw or "").strip()).strip()
        if not payload_text:
            return _Extraction()
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            # Some local models still prepend commentary; try to salvage the first
            # JSON object heuristically rather than silently dropping the reply.
            brace_start = payload_text.find("{")
            brace_end = payload_text.rfind("}")
            if brace_start == -1 or brace_end <= brace_start:
                return _Extraction()
            try:
                payload = json.loads(payload_text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                return _Extraction()
        try:
            return _Extraction.model_validate(payload)
        except PydanticValidationError:
            return _Extraction()

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
    def _deduplicate(offers: list[_Offer]) -> list[_Offer]:
        best: dict[str, _Offer] = {}
        for offer in offers:
            category = offer.category.strip()
            if not category or offer.percent <= 0 or offer.percent > 100:
                continue
            key = category.casefold()
            current = best.get(key)
            if current is None or offer.percent > current.percent:
                best[key] = _Offer(category=category, percent=offer.percent)
        return sorted(best.values(), key=lambda item: (-item.percent, item.category.casefold()))
