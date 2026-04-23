from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.adapters.ocr_claude_vision.service import (
    ClaudeVisionOCRAdapter,
    _CashbackExtraction,
    _CashbackOffer,
)
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError


_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff"
    b"?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload(content: bytes = _PNG_1x1, *, content_type: str = "image/png") -> ImageUpload:
    return ImageUpload(content=content, filename="screenshot.png", content_type=content_type)


def _build_adapter(*, max_file_size: int = 1024 * 1024, timeout: int = 5) -> ClaudeVisionOCRAdapter:
    return ClaudeVisionOCRAdapter(
        api_key="test-key",
        model="claude-opus-4-7",
        timeout=timeout,
        max_file_size=max_file_size,
    )


def _install_fake_claude(
    adapter: ClaudeVisionOCRAdapter,
    *,
    offers: list[_CashbackOffer] | None = None,
    raises: BaseException | None = None,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    async def fake_parse(**kwargs):
        captured["kwargs"] = kwargs
        if raises is not None:
            raise raises
        return SimpleNamespace(parsed_output=_CashbackExtraction(offers=offers or []))

    adapter._client = SimpleNamespace(messages=SimpleNamespace(parse=fake_parse))
    return captured


@pytest.mark.asyncio
async def test_extract_text_formats_offers_for_parser() -> None:
    adapter = _build_adapter()
    _install_fake_claude(
        adapter,
        offers=[
            _CashbackOffer(category="АЗС", percent=5),
            _CashbackOffer(category="Рестораны", percent=10),
            _CashbackOffer(category="Аптеки", percent=3.5),
        ],
    )

    text = await adapter.extract_text(_upload())

    lines = text.splitlines()
    assert lines[0] == "Рестораны: 10%"
    assert lines[1] == "АЗС: 5%"
    assert lines[2] == "Аптеки: 3.5%"


@pytest.mark.asyncio
async def test_extract_text_deduplicates_and_keeps_highest_percent() -> None:
    adapter = _build_adapter()
    _install_fake_claude(
        adapter,
        offers=[
            _CashbackOffer(category="Супермаркеты", percent=2),
            _CashbackOffer(category="супермаркеты", percent=7),
            _CashbackOffer(category="АЗС", percent=5),
        ],
    )

    text = await adapter.extract_text(_upload())

    # Highest-percent duplicate wins; the parser later normalizes casing to a slug.
    assert text.splitlines() == ["супермаркеты: 7%", "АЗС: 5%"]


@pytest.mark.asyncio
async def test_extract_text_rejects_zero_and_out_of_range_percent() -> None:
    adapter = _build_adapter()
    _install_fake_claude(
        adapter,
        offers=[
            _CashbackOffer(category="АЗС", percent=5),
            # Invalid entries must be dropped silently so Claude's occasional
            # over-extraction doesn't poison the draft.
            _CashbackOffer(category="Noise", percent=0),
        ],
    )

    text = await adapter.extract_text(_upload())

    assert text == "АЗС: 5%"


@pytest.mark.asyncio
async def test_extract_text_raises_when_no_offers_recognized() -> None:
    adapter = _build_adapter()
    _install_fake_claude(adapter, offers=[])

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
async def test_extract_text_rejects_broken_binary() -> None:
    adapter = _build_adapter()
    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload(content=b"not-an-image", content_type="application/octet-stream"))
    assert error.value.message_key == "errors.broken_image"


@pytest.mark.asyncio
async def test_extract_text_sends_image_and_schema_to_claude() -> None:
    adapter = _build_adapter()
    captured = _install_fake_claude(
        adapter,
        offers=[_CashbackOffer(category="АЗС", percent=5)],
    )

    await adapter.extract_text(_upload())

    kwargs = captured["kwargs"]
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["output_format"] is _CashbackExtraction
    assert kwargs["max_tokens"] >= 256
    content = kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["type"] == "base64"
    assert content[0]["source"]["media_type"] == "image/png"
    assert isinstance(content[0]["source"]["data"], str) and content[0]["source"]["data"]
    assert content[1]["type"] == "text"


@pytest.mark.asyncio
async def test_extract_text_maps_timeout_to_validation_error() -> None:
    adapter = _build_adapter(timeout=1)

    async def slow_parse(**_kwargs):
        await asyncio.sleep(5)
        return SimpleNamespace(parsed_output=_CashbackExtraction())

    adapter._client = SimpleNamespace(messages=SimpleNamespace(parse=slow_parse))

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())
    assert error.value.message_key == "errors.ocr_timeout"


def test_constructor_requires_api_key() -> None:
    with pytest.raises(ValueError):
        ClaudeVisionOCRAdapter(api_key="")
