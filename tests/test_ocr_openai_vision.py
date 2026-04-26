from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from app.adapters.ocr_openai_vision.service import (
    OpenAIVisionOCRAdapter,
    _Extraction,
    _Offer,
)
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError

# Minimal valid 1x1 PNG so PIL can sniff the format when content-type is missing.
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff"
    b"?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload(content: bytes = _PNG_1x1, *, content_type: str = "image/png") -> ImageUpload:
    return ImageUpload(content=content, filename="screenshot.png", content_type=content_type)


def _build_adapter(*, max_file_size: int = 1024 * 1024, timeout: int = 5) -> OpenAIVisionOCRAdapter:
    return OpenAIVisionOCRAdapter(
        api_key="sk-test-123",
        model="gpt-4o",
        timeout=timeout,
        max_file_size=max_file_size,
    )


def _install_fake_completion(
    adapter: OpenAIVisionOCRAdapter,
    *,
    content: str | None = None,
    raises: BaseException | None = None,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_create(**kwargs):
        captured["kwargs"] = kwargs
        if raises is not None:
            raise raises
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content or ""))])

    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    return captured


def _json_content(offers: list[dict[str, Any]]) -> str:
    return json.dumps({"offers": offers}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_extract_text_formats_offers_for_parser() -> None:
    adapter = _build_adapter()
    _install_fake_completion(
        adapter,
        content=_json_content(
            [
                {"category": "АЗС", "percent": 5},
                {"category": "Рестораны", "percent": 10},
                {"category": "Аптеки", "percent": 3.5},
            ]
        ),
    )

    text = await adapter.extract_text(_upload())

    assert text.splitlines() == [
        "Рестораны: 10%",
        "АЗС: 5%",
        "Аптеки: 3.5%",
    ]


@pytest.mark.asyncio
async def test_extract_text_strips_markdown_fence() -> None:
    adapter = _build_adapter()
    _install_fake_completion(
        adapter,
        content="```json\n" + _json_content([{"category": "АЗС", "percent": 5}]) + "\n```",
    )

    text = await adapter.extract_text(_upload())

    assert text == "АЗС: 5%"


@pytest.mark.asyncio
async def test_extract_text_salvages_json_with_leading_commentary() -> None:
    adapter = _build_adapter()
    # Some local vision models prepend commentary before the JSON object.
    noisy = 'Here is the extracted data:\n{"offers": [{"category": "АЗС", "percent": 5}]}'
    _install_fake_completion(adapter, content=noisy)

    text = await adapter.extract_text(_upload())

    assert text == "АЗС: 5%"


@pytest.mark.asyncio
async def test_extract_text_deduplicates_and_keeps_highest_percent() -> None:
    adapter = _build_adapter()
    _install_fake_completion(
        adapter,
        content=_json_content(
            [
                {"category": "Супермаркеты", "percent": 2},
                {"category": "супермаркеты", "percent": 7},
                {"category": "АЗС", "percent": 5},
            ]
        ),
    )

    text = await adapter.extract_text(_upload())

    # Highest-percent duplicate wins; parser then normalizes casing to a slug.
    assert text.splitlines() == ["супермаркеты: 7%", "АЗС: 5%"]


@pytest.mark.asyncio
async def test_extract_text_filters_invalid_percents_and_blank_categories() -> None:
    adapter = _build_adapter()
    _install_fake_completion(
        adapter,
        content=_json_content(
            [
                {"category": "АЗС", "percent": 5},
                {"category": "   ", "percent": 10},  # blank category
                {"category": "Noise", "percent": 0},  # zero percent
            ]
        ),
    )

    text = await adapter.extract_text(_upload())

    assert text == "АЗС: 5%"


@pytest.mark.asyncio
async def test_extract_text_raises_when_no_offers_recognized() -> None:
    adapter = _build_adapter()
    _install_fake_completion(adapter, content=_json_content([]))

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())
    assert error.value.message_key == "errors.ocr_empty"


@pytest.mark.asyncio
async def test_extract_text_raises_on_malformed_json() -> None:
    adapter = _build_adapter()
    _install_fake_completion(adapter, content="this response is not json at all")

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())
    assert error.value.message_key == "errors.ocr_empty"


@pytest.mark.asyncio
async def test_extract_text_raises_on_wrong_schema_shape() -> None:
    adapter = _build_adapter()
    # Pydantic validation must reject payloads that don't match our schema.
    _install_fake_completion(
        adapter,
        content=json.dumps({"wrong_key": [{"category": "АЗС", "percent": 5}]}),
    )

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())
    assert error.value.message_key == "errors.ocr_empty"


@pytest.mark.asyncio
async def test_extract_text_handles_empty_choices() -> None:
    adapter = _build_adapter()

    async def empty_choices(**_kwargs):
        return SimpleNamespace(choices=[])

    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=empty_choices)))

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())
    assert error.value.message_key == "errors.ocr_empty"


@pytest.mark.asyncio
async def test_extract_text_rejects_empty_upload() -> None:
    adapter = _build_adapter()
    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload(content=b""))
    assert error.value.message_key == "errors.broken_image"


@pytest.mark.asyncio
async def test_extract_text_rejects_too_large_upload() -> None:
    adapter = _build_adapter(max_file_size=16)
    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload(content=b"x" * 32))
    assert error.value.message_key == "errors.file_too_large"


@pytest.mark.asyncio
async def test_extract_text_rejects_broken_binary_without_declared_type() -> None:
    adapter = _build_adapter()
    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload(content=b"not-an-image", content_type="application/octet-stream"))
    assert error.value.message_key == "errors.broken_image"


@pytest.mark.asyncio
async def test_extract_text_sends_image_data_url_and_json_mode() -> None:
    adapter = _build_adapter()
    captured = _install_fake_completion(adapter, content=_json_content([{"category": "АЗС", "percent": 5}]))

    await adapter.extract_text(_upload())

    kwargs = captured["kwargs"]
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["response_format"] == {"type": "json_object"}
    # System message must mention JSON for json_object mode to work on real OpenAI.
    system_content = kwargs["messages"][0]["content"]
    assert "JSON" in system_content

    user_parts = kwargs["messages"][1]["content"]
    types = {part["type"] for part in user_parts}
    assert {"text", "image_url"} <= types
    image_part = next(p for p in user_parts if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert image_part["image_url"]["detail"] == "high"


@pytest.mark.asyncio
async def test_extract_text_infers_media_type_from_png_bytes_when_content_type_missing() -> None:
    adapter = _build_adapter()
    captured = _install_fake_completion(adapter, content=_json_content([{"category": "АЗС", "percent": 5}]))

    await adapter.extract_text(_upload(content_type=""))

    image_part = next(p for p in captured["kwargs"]["messages"][1]["content"] if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_extract_text_normalizes_jpg_alias_to_jpeg() -> None:
    adapter = _build_adapter()
    captured = _install_fake_completion(adapter, content=_json_content([{"category": "АЗС", "percent": 5}]))

    await adapter.extract_text(_upload(content_type="image/jpg"))

    image_part = next(p for p in captured["kwargs"]["messages"][1]["content"] if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_extract_text_maps_wait_for_timeout_to_validation_error() -> None:
    adapter = _build_adapter(timeout=1)

    async def slow_create(**_kwargs):
        await asyncio.sleep(5)

    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=slow_create)))

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())
    assert error.value.message_key == "errors.ocr_timeout"


def _mock_http_request() -> httpx.Request:
    return httpx.Request("POST", "https://example.test/v1/chat/completions")


def _mock_http_response(status: int) -> httpx.Response:
    return httpx.Response(status_code=status, request=_mock_http_request())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_factory", "expected_key"),
    [
        (lambda: APITimeoutError(_mock_http_request()), "errors.ocr_timeout"),
        (lambda: APIConnectionError(request=_mock_http_request()), "errors.ocr_timeout"),
        (
            lambda: RateLimitError(
                "rate limited",
                response=_mock_http_response(429),
                body=None,
            ),
            "errors.ocr_timeout",
        ),
        (
            lambda: BadRequestError(
                "bad request",
                response=_mock_http_response(400),
                body=None,
            ),
            "errors.broken_image",
        ),
        (
            lambda: AuthenticationError(
                "unauthorized",
                response=_mock_http_response(401),
                body=None,
            ),
            "errors.ocr_timeout",
        ),
        (
            lambda: APIError("server error", request=_mock_http_request(), body=None),
            "errors.ocr_timeout",
        ),
    ],
)
async def test_extract_text_maps_sdk_errors_to_validation_errors(error_factory, expected_key) -> None:
    adapter = _build_adapter()
    _install_fake_completion(adapter, raises=error_factory())

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())
    assert error.value.message_key == expected_key


@pytest.mark.asyncio
async def test_extract_text_offloads_base64_to_executor_so_event_loop_stays_responsive() -> None:
    # If _prepare_image ran on the event loop, a large upload would block it. Prove it's
    # off-loaded by making the upload's content appear 'small' to the main thread but
    # verifying that the executor is invoked (prepare_image records its thread).
    import threading

    adapter = _build_adapter()
    captured_thread: dict[str, Any] = {}
    original_prepare = adapter._prepare_image

    def spy_prepare(upload: ImageUpload) -> tuple[str, str]:
        captured_thread["thread"] = threading.current_thread()
        return original_prepare(upload)

    adapter._prepare_image = spy_prepare  # type: ignore[method-assign]
    _install_fake_completion(adapter, content=_json_content([{"category": "АЗС", "percent": 5}]))

    await adapter.extract_text(_upload())

    assert captured_thread["thread"] is not threading.main_thread()


def test_constructor_requires_api_key() -> None:
    with pytest.raises(ValueError):
        OpenAIVisionOCRAdapter(api_key="")


def test_constructor_applies_custom_base_url() -> None:
    adapter = OpenAIVisionOCRAdapter(
        api_key="sk-test-123",
        base_url="https://api.proxyapi.ru/openai/v1",
    )
    assert str(adapter._client.base_url).startswith("https://api.proxyapi.ru/openai/v1")


def test_parse_extraction_rejects_percent_out_of_bounds_via_pydantic() -> None:
    extraction = OpenAIVisionOCRAdapter._parse_extraction(
        json.dumps({"offers": [{"category": "АЗС", "percent": 150}]})
    )
    # Pydantic validation on the schema rejects out-of-bounds values; deduplicate never sees them.
    assert extraction.offers == []


def test_deduplicate_is_stable_between_equal_percents() -> None:
    offers = [
        _Offer(category="A", percent=5),
        _Offer(category="B", percent=5),
    ]
    result = OpenAIVisionOCRAdapter._deduplicate(offers)
    # Stable alphabetical tie-break keeps the behavior predictable for UI rendering.
    assert [o.category for o in result] == ["A", "B"]


def test_parse_extraction_on_empty_input_returns_empty_extraction() -> None:
    assert OpenAIVisionOCRAdapter._parse_extraction("") == _Extraction()
    assert OpenAIVisionOCRAdapter._parse_extraction("   ") == _Extraction()
