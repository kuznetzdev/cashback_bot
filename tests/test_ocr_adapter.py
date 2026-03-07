from __future__ import annotations

import time
from pathlib import Path

import pytest
from PIL import Image
import pytesseract

from app.adapters.ocr_tesseract.service import TesseractOCRAdapter
from app.domain.errors import ValidationError


@pytest.mark.asyncio
async def test_ocr_adapter_extracts_text_with_stubbed_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (80, 40), color="white").save(image_path, format="PNG")

    adapter = TesseractOCRAdapter(
        tesseract_path="tesseract",
        timeout=3,
        max_file_size=1024 * 1024,
        temp_dir=tmp_path / "ocr",
    )
    monkeypatch.setattr(TesseractOCRAdapter, "_ocr", staticmethod(lambda _: "АЗС 5%"))

    text = await adapter.extract_text(image_path)
    assert text == "АЗС 5%"


@pytest.mark.asyncio
async def test_ocr_adapter_rejects_large_files(tmp_path: Path) -> None:
    large_file = tmp_path / "large.bin"
    large_file.write_bytes(b"0" * 2048)

    adapter = TesseractOCRAdapter(
        tesseract_path="tesseract",
        timeout=3,
        max_file_size=1024,
        temp_dir=tmp_path / "ocr",
    )
    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(large_file)
    assert error.value.message_key == "errors.file_too_large"


@pytest.mark.asyncio
async def test_ocr_adapter_handles_broken_image(tmp_path: Path) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"this-is-not-image-data")

    adapter = TesseractOCRAdapter(
        tesseract_path="tesseract",
        timeout=3,
        max_file_size=1024 * 1024,
        temp_dir=tmp_path / "ocr",
    )
    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(broken)
    assert error.value.message_key == "errors.broken_image"


@pytest.mark.asyncio
async def test_ocr_adapter_timeout_maps_to_validation_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "slow.png"
    Image.new("RGB", (80, 40), color="white").save(image_path, format="PNG")

    adapter = TesseractOCRAdapter(
        tesseract_path="tesseract",
        timeout=1,
        max_file_size=1024 * 1024,
        temp_dir=tmp_path / "ocr",
    )

    def _slow_preprocess(_source: Path, _target: Path) -> None:
        time.sleep(2)

    monkeypatch.setattr(TesseractOCRAdapter, "_preprocess", staticmethod(_slow_preprocess))

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(image_path)
    assert error.value.message_key == "errors.ocr_timeout"


def test_ocr_adapter_uses_tesseract_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "ocr.png"
    Image.new("RGB", (80, 40), color="white").save(image_path, format="PNG")
    captured: dict[str, object] = {}

    def _fake_image_to_string(_image, **kwargs):
        captured.update(kwargs)
        return "АЗС 5%"

    monkeypatch.setattr(pytesseract, "image_to_string", _fake_image_to_string)
    text = TesseractOCRAdapter._ocr(image_path)

    assert text == "АЗС 5%"
    assert captured["lang"] == "rus+eng"
    assert captured["config"] == "--oem 3 --psm 6 -c preserve_interword_spaces=1"
