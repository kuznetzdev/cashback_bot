"""Unit tests for the Tesseract preprocessing helpers. We deliberately test
the pure-Python pieces (dark-theme auto-inversion) instead of the full
pipeline, because the full pipeline requires the Tesseract binary and a
large fixture corpus. The inversion heuristic is the part most likely to
regress and the cheapest to cover.
"""

from __future__ import annotations

from PIL import Image

from app.adapters.ocr_tesseract.service import _autoinvert_if_dark


def _solid(value: int, size: tuple[int, int] = (256, 256)) -> Image.Image:
    return Image.new("L", size, color=value)


def test_light_image_passes_through_unchanged() -> None:
    # Mean ~240 (light screen), threshold 96 → no inversion.
    light = _solid(240)
    result = _autoinvert_if_dark(light, threshold=96)
    # The helper returns the same pixel distribution (it's the same object OR a copy
    # with identical data) — sample a pixel to verify.
    assert result.getpixel((10, 10)) == 240


def test_dark_image_gets_inverted() -> None:
    # Mean ~20 (dark-mode screen), threshold 96 → invert.
    dark = _solid(20)
    result = _autoinvert_if_dark(dark, threshold=96)
    # Inversion: 20 → 235.
    assert result.getpixel((10, 10)) == 235


def test_medium_brightness_does_not_invert() -> None:
    # Mean ~128, above threshold → keep as-is. This is the edge case where we
    # must NOT incorrectly invert a neutral-brightness screenshot.
    medium = _solid(128)
    result = _autoinvert_if_dark(medium, threshold=96)
    assert result.getpixel((10, 10)) == 128


def test_threshold_boundary_is_exclusive() -> None:
    # Pixel value exactly at threshold → do not invert (strict less-than).
    at_threshold = _solid(96)
    result = _autoinvert_if_dark(at_threshold, threshold=96)
    assert result.getpixel((10, 10)) == 96
