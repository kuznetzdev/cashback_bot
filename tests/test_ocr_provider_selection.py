from __future__ import annotations

import pytest

from app.adapters.ocr_claude_vision import ClaudeVisionOCRAdapter
from app.adapters.ocr_tesseract import TesseractOCRAdapter
from app.bootstrap.config import Settings
from app.bootstrap.container import _build_ocr_adapter


def _settings(**overrides) -> Settings:
    # Ensure we always start from clean defaults; tests override env via kwargs.
    defaults = dict(BOT_TOKEN="123456:unit_test")
    defaults.update(overrides)
    return Settings(**defaults)


def test_auto_without_key_picks_tesseract() -> None:
    adapter = _build_ocr_adapter(_settings(OCR_PROVIDER="auto", ANTHROPIC_API_KEY=""))
    assert isinstance(adapter, TesseractOCRAdapter)


def test_auto_with_key_picks_claude_vision() -> None:
    adapter = _build_ocr_adapter(
        _settings(OCR_PROVIDER="auto", ANTHROPIC_API_KEY="sk-test-123")
    )
    assert isinstance(adapter, ClaudeVisionOCRAdapter)


def test_explicit_tesseract_ignores_key() -> None:
    adapter = _build_ocr_adapter(
        _settings(OCR_PROVIDER="tesseract", ANTHROPIC_API_KEY="sk-test-123")
    )
    assert isinstance(adapter, TesseractOCRAdapter)


def test_explicit_claude_requires_key() -> None:
    with pytest.raises(ValueError):
        _build_ocr_adapter(_settings(OCR_PROVIDER="claude", ANTHROPIC_API_KEY=""))


def test_explicit_claude_with_key_uses_configured_model() -> None:
    adapter = _build_ocr_adapter(
        _settings(
            OCR_PROVIDER="claude",
            ANTHROPIC_API_KEY="sk-test-123",
            ANTHROPIC_MODEL="claude-haiku-4-5",
        )
    )
    assert isinstance(adapter, ClaudeVisionOCRAdapter)
    assert adapter._model == "claude-haiku-4-5"
