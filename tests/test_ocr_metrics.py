from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.ocr_metrics import MetricsOCRAdapter
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError


def _upload() -> ImageUpload:
    return ImageUpload(content=b"\x89PNG\x0d\x0a\x1a\x0a" + b"\x00" * 32,
                       filename="test.png",
                       content_type="image/png")


def _counter_probe() -> MagicMock:
    counter = MagicMock()
    counter.labels = MagicMock(return_value=MagicMock())
    return counter


@pytest.mark.asyncio
async def test_metrics_wrapper_records_ok_on_successful_extraction() -> None:
    inner = MagicMock()
    inner.extract_text = AsyncMock(return_value="АЗС 5%\nРестораны 3%")
    counter = _counter_probe()

    wrapped = MetricsOCRAdapter(inner, provider="tesseract", counter=counter)
    text = await wrapped.extract_text(_upload())

    assert text == "АЗС 5%\nРестораны 3%"
    counter.labels.assert_called_once_with(provider="tesseract", result="ok")
    counter.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_metrics_wrapper_records_empty_on_blank_text() -> None:
    inner = MagicMock()
    inner.extract_text = AsyncMock(return_value="   \n\n")
    counter = _counter_probe()

    wrapped = MetricsOCRAdapter(inner, provider="openai", counter=counter)
    await wrapped.extract_text(_upload())

    counter.labels.assert_called_once_with(provider="openai", result="empty")


@pytest.mark.asyncio
async def test_metrics_wrapper_records_empty_from_validation_error() -> None:
    inner = MagicMock()
    inner.extract_text = AsyncMock(side_effect=ValidationError("errors.ocr_empty"))
    counter = _counter_probe()

    wrapped = MetricsOCRAdapter(inner, provider="tesseract", counter=counter)
    with pytest.raises(ValidationError):
        await wrapped.extract_text(_upload())

    counter.labels.assert_called_once_with(provider="tesseract", result="empty")


@pytest.mark.asyncio
async def test_metrics_wrapper_records_timeout() -> None:
    inner = MagicMock()
    inner.extract_text = AsyncMock(side_effect=ValidationError("errors.ocr_timeout"))
    counter = _counter_probe()

    wrapped = MetricsOCRAdapter(inner, provider="tesseract", counter=counter)
    with pytest.raises(ValidationError):
        await wrapped.extract_text(_upload())

    counter.labels.assert_called_once_with(provider="tesseract", result="timeout")


@pytest.mark.asyncio
async def test_metrics_wrapper_records_generic_error_on_other_validation() -> None:
    inner = MagicMock()
    inner.extract_text = AsyncMock(side_effect=ValidationError("errors.broken_image"))
    counter = _counter_probe()

    wrapped = MetricsOCRAdapter(inner, provider="openai", counter=counter)
    with pytest.raises(ValidationError):
        await wrapped.extract_text(_upload())

    counter.labels.assert_called_once_with(provider="openai", result="error")


@pytest.mark.asyncio
async def test_metrics_wrapper_records_error_on_unhandled_exception() -> None:
    inner = MagicMock()
    inner.extract_text = AsyncMock(side_effect=RuntimeError("network"))
    counter = _counter_probe()

    wrapped = MetricsOCRAdapter(inner, provider="composite", counter=counter)
    with pytest.raises(RuntimeError):
        await wrapped.extract_text(_upload())

    counter.labels.assert_called_once_with(provider="composite", result="error")


@pytest.mark.asyncio
async def test_metrics_wrapper_does_not_break_on_counter_failure() -> None:
    inner = MagicMock()
    inner.extract_text = AsyncMock(return_value="text")

    class _BrokenCounter:
        def labels(self, **_):
            raise RuntimeError("metrics backend down")

    wrapped = MetricsOCRAdapter(inner, provider="tesseract", counter=_BrokenCounter())
    # Should still return the real OCR output, not re-raise from the counter.
    assert await wrapped.extract_text(_upload()) == "text"
