from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.adapters.ocr_composite import CompositeOCRAdapter
from app.application.contracts.ports import OCRPort
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError


@dataclass
class _StubOCR(OCRPort):
    """Scriptable OCR port — returns the configured text or raises the
    configured error. Call count is tracked so tests can assert on whether
    the fallback was actually invoked."""

    text: str | None = None
    error: ValidationError | None = None
    calls: int = 0

    async def extract_text(self, upload: ImageUpload) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.text is not None
        return self.text


def _upload() -> ImageUpload:
    return ImageUpload(content=b"ignored", filename="x.png", content_type="image/png")


@pytest.mark.asyncio
async def test_primary_succeeds_no_fallback_invoked() -> None:
    primary = _StubOCR(text="АЗС: 5%")
    fallback = _StubOCR(text="Рестораны: 10%")
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback)

    result = await adapter.extract_text(_upload())

    assert result == "АЗС: 5%"
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_empty_primary_escalates_to_fallback() -> None:
    primary = _StubOCR(error=ValidationError("errors.ocr_empty"))
    fallback = _StubOCR(text="Рестораны: 10%")
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback)

    result = await adapter.extract_text(_upload())

    assert result == "Рестораны: 10%"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_timeout_primary_escalates_to_fallback() -> None:
    primary = _StubOCR(error=ValidationError("errors.ocr_timeout"))
    fallback = _StubOCR(text="АЗС: 5%")
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback)

    result = await adapter.extract_text(_upload())

    assert result == "АЗС: 5%"
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_broken_image_does_not_escalate() -> None:
    # broken_image means the upload is fundamentally bad; both engines would
    # fail equally, so paying for the AI round-trip is wasteful.
    primary = _StubOCR(error=ValidationError("errors.broken_image"))
    fallback = _StubOCR(text="should not be reached")
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback)

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())

    assert error.value.message_key == "errors.broken_image"
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_file_too_large_does_not_escalate() -> None:
    primary = _StubOCR(error=ValidationError("errors.file_too_large"))
    fallback = _StubOCR(text="should not be reached")
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback)

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())

    assert error.value.message_key == "errors.file_too_large"
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_fallback_also_fails_surfaces_fallback_error() -> None:
    primary = _StubOCR(error=ValidationError("errors.ocr_empty"))
    # AI also couldn't parse → user sees the AI's error key, not the local one.
    fallback = _StubOCR(error=ValidationError("errors.ocr_timeout"))
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback)

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())

    assert error.value.message_key == "errors.ocr_timeout"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_no_fallback_configured_raises_primary_error() -> None:
    primary = _StubOCR(error=ValidationError("errors.ocr_empty"))
    adapter = CompositeOCRAdapter(primary=primary, fallback=None)

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())

    assert error.value.message_key == "errors.ocr_empty"
