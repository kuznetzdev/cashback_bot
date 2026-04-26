from __future__ import annotations

import pytest

from app.adapters.ocr_composite import CompositeOCRAdapter
from app.adapters.ocr_openai_vision import OpenAIVisionOCRAdapter
from app.adapters.ocr_tesseract import TesseractOCRAdapter
from app.bootstrap.config import Settings
from app.bootstrap.container import _build_ocr_adapter


def _settings(**overrides) -> Settings:
    # Ensure we always start from clean defaults; tests override env via kwargs.
    defaults = dict(BOT_TOKEN="123456:unit_test")
    defaults.update(overrides)
    return Settings(**defaults)


def test_auto_without_key_picks_tesseract() -> None:
    adapter = _build_ocr_adapter(_settings(OCR_PROVIDER="auto", OPENAI_API_KEY=""))
    assert isinstance(adapter, TesseractOCRAdapter)


def test_auto_with_key_picks_composite_tesseract_first_openai_fallback() -> None:
    adapter = _build_ocr_adapter(_settings(OCR_PROVIDER="auto", OPENAI_API_KEY="sk-test-123"))
    # Local-first: primary is Tesseract (free), fallback is OpenAI (billed).
    assert isinstance(adapter, CompositeOCRAdapter)
    assert isinstance(adapter._primary, TesseractOCRAdapter)
    assert isinstance(adapter._fallback, OpenAIVisionOCRAdapter)


def test_explicit_tesseract_ignores_key() -> None:
    adapter = _build_ocr_adapter(_settings(OCR_PROVIDER="tesseract", OPENAI_API_KEY="sk-test-123"))
    assert isinstance(adapter, TesseractOCRAdapter)


def test_explicit_openai_requires_key() -> None:
    with pytest.raises(ValueError):
        _build_ocr_adapter(_settings(OCR_PROVIDER="openai", OPENAI_API_KEY=""))


def test_explicit_openai_with_key_uses_configured_model() -> None:
    adapter = _build_ocr_adapter(
        _settings(
            OCR_PROVIDER="openai",
            OPENAI_API_KEY="sk-test-123",
            OPENAI_MODEL="gpt-4o-mini",
        )
    )
    assert isinstance(adapter, OpenAIVisionOCRAdapter)
    assert adapter._model == "gpt-4o-mini"


def test_explicit_openai_accepts_custom_base_url() -> None:
    adapter = _build_ocr_adapter(
        _settings(
            OCR_PROVIDER="openai",
            OPENAI_API_KEY="sk-test-123",
            OPENAI_BASE_URL="https://api.proxyapi.ru/openai/v1",
        )
    )
    assert isinstance(adapter, OpenAIVisionOCRAdapter)
    # Configured base URL must be what the OpenAI client uses — otherwise proxies silently break.
    assert str(adapter._client.base_url).startswith("https://api.proxyapi.ru/openai/v1")


def test_unknown_provider_raises_with_valid_options_in_message() -> None:
    with pytest.raises(ValueError) as error:
        _build_ocr_adapter(_settings(OCR_PROVIDER="invalid"))
    message = str(error.value)
    assert "invalid" in message
    assert "tesseract" in message
    assert "openai" in message
    assert "auto" in message
