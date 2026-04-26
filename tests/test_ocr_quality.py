"""Quality tests for image-recognition pipeline and OCR artifact filtering.

Pins:
 - CompositeOCR content-validator escalates to AI when Tesseract returns
   syntactically-OK text with no parseable offers.
 - Tesseract preprocessing uses LANCZOS and UnsharpMask (shape-level test,
   not a vision-quality test — we can't run Tesseract in CI).
 - Parser rejects OCR-artifact categories (single char, digits-only,
   punctuation-only) so "5% 3% 7%" garbage doesn't polute a draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.adapters.ocr_composite import CompositeOCRAdapter
from app.application.contracts.ports import OCRPort
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService

# --- CompositeOCR content validator ------------------------------------------


@dataclass
class _StubOCR(OCRPort):
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
async def test_composite_escalates_when_primary_returns_unparseable_text() -> None:
    # Tesseract "saw" a screenshot but extracted a wall of punctuation — no
    # percent signs, no cashback. The composite must still escalate to the AI
    # fallback so the user gets a real answer.
    garbage = "--- --- !@# ??? ...\n...\n@@@"

    def looks_parseable(text: str) -> bool:
        # Minimal inline check: we require at least a digit + a '%' + a letter.
        return bool("%" in text and any(ch.isdigit() for ch in text) and any(ch.isalpha() for ch in text))

    primary = _StubOCR(text=garbage)
    fallback = _StubOCR(text="АЗС: 5%\nРестораны: 10%")
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback, content_validator=looks_parseable)

    result = await adapter.extract_text(_upload())

    assert "Рестораны" in result
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_composite_does_not_escalate_when_primary_text_passes_validator() -> None:
    def looks_parseable(text: str) -> bool:
        return "%" in text

    primary = _StubOCR(text="АЗС: 5%")
    fallback = _StubOCR(text="SHOULD NOT BE CALLED")
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback, content_validator=looks_parseable)

    result = await adapter.extract_text(_upload())

    assert result == "АЗС: 5%"
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_composite_with_failing_validator_but_no_fallback_returns_primary() -> None:
    # If we configured a validator but no fallback adapter, we can't escalate.
    # In that case return whatever the primary produced so downstream parsing
    # can raise its own empty-offers error — we don't want to silently drop
    # the only result we have.
    primary = _StubOCR(text="garbage")
    adapter = CompositeOCRAdapter(primary=primary, fallback=None, content_validator=lambda text: False)

    assert await adapter.extract_text(_upload()) == "garbage"


@pytest.mark.asyncio
async def test_composite_validator_fallback_error_propagates() -> None:
    def looks_parseable(_text: str) -> bool:
        return False

    primary = _StubOCR(text="garbage")
    fallback = _StubOCR(error=ValidationError("errors.ocr_timeout"))
    adapter = CompositeOCRAdapter(primary=primary, fallback=fallback, content_validator=looks_parseable)

    with pytest.raises(ValidationError) as error:
        await adapter.extract_text(_upload())
    assert error.value.message_key == "errors.ocr_timeout"


@pytest.mark.asyncio
async def test_composite_uses_parser_as_default_validator_shape() -> None:
    # Integration-style check: when the validator IS the parser, garbage text
    # escalates and clean text doesn't. Locks the contract the container wires.
    parser = ParserService(CategoryService())

    def parser_validator(text: str) -> bool:
        try:
            return bool(parser.parse_ocr_text(text))
        except Exception:
            return False

    primary_garbage = _StubOCR(text="foo bar baz")
    fallback = _StubOCR(text="АЗС: 5%")
    adapter = CompositeOCRAdapter(
        primary=primary_garbage, fallback=fallback, content_validator=parser_validator
    )
    assert (await adapter.extract_text(_upload())).startswith("АЗС")

    primary_clean = _StubOCR(text="АЗС: 5%")
    untouched = _StubOCR(text="SHOULD NOT RUN")
    adapter2 = CompositeOCRAdapter(
        primary=primary_clean, fallback=untouched, content_validator=parser_validator
    )
    assert await adapter2.extract_text(_upload()) == "АЗС: 5%"
    assert untouched.calls == 0


# --- Parser artifact filtering ----------------------------------------------


@pytest.fixture(scope="module")
def parser() -> ParserService:
    return ParserService(CategoryService())


@pytest.mark.parametrize(
    "line",
    [
        "% 5%",  # punctuation-only category
        "1 2.5%",  # digit-only category
        "- 3%",  # dash "category"
        ". . 4%",  # dots
        "5 7%",  # two numbers, no letters — classic OCR artifact
    ],
)
def test_parser_drops_ocr_artifact_categories(parser: ParserService, line: str) -> None:
    # Parser returns an empty list (via parse_ocr_text) instead of pretending
    # that "5" or "%" is a category. parse_manual_lines would raise — that's
    # also acceptable upstream.
    items = parser.parse_ocr_text(line)
    assert items == []


def test_parser_keeps_single_word_valid_category(parser: ParserService) -> None:
    # A real short word like "Кино" must still parse — the filter is for
    # non-letter strings, not for short words.
    items = parser.parse_ocr_text("Кино 5%")
    assert len(items) == 1
    assert items[0].normalized_category == "movies"


def test_parser_rejects_one_letter_category(parser: ParserService) -> None:
    # "А 5%" — Cyrillic single letter. Category of length 1 is almost
    # certainly OCR noise, not a real offer name.
    items = parser.parse_ocr_text("А 5%")
    assert items == []


# --- Tesseract preprocessing shape tests ------------------------------------


def _solid_png(size: tuple[int, int] = (200, 200), value: int = 220) -> bytes:
    img = Image.new("L", size, color=value).convert("RGB")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_preprocess_produces_valid_png(tmp_path: Path) -> None:
    from app.adapters.ocr_tesseract.service import TesseractOCRAdapter

    src = _solid_png()
    target = tmp_path / "out.png"
    TesseractOCRAdapter._preprocess(src, target)

    assert target.exists()
    with Image.open(target) as out:
        # Image was upscaled 2× — shape check.
        assert out.size == (400, 400)
        assert out.mode == "L"  # still grayscale after the pipeline


def test_preprocess_dark_image_gets_inverted_in_pipeline(tmp_path: Path) -> None:
    # Dark-dominant input (value=20) should come out light-dominant after the
    # auto-invert step runs during preprocessing.
    from PIL import ImageStat

    from app.adapters.ocr_tesseract.service import TesseractOCRAdapter

    src = _solid_png(value=20)
    target = tmp_path / "out.png"
    TesseractOCRAdapter._preprocess(src, target)

    with Image.open(target) as out:
        mean = ImageStat.Stat(out).mean[0]
        # Post-inversion + autocontrast — expect a clearly-light image.
        assert mean > 200, f"expected light post-invert output, got mean={mean}"
