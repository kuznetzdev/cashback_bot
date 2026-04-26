from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytesseract
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.adapters._shared import validate_image_upload
from app.application.contracts.ports import OCRPort
from app.application.dto.media import ImageUpload
from app.domain.errors import ValidationError

logger = logging.getLogger(__name__)


class TesseractOCRAdapter(OCRPort):
    def __init__(self, *, tesseract_path: str, timeout: int, max_file_size: int, temp_dir: Path) -> None:
        self.timeout = timeout
        self.max_file_size = max_file_size
        self.temp_dir = temp_dir
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        self._sweep_temp_dir_on_startup()

    def _sweep_temp_dir_on_startup(self) -> None:
        """If a previous process crashed mid-OCR, PNG intermediates are left
        behind. Sweep the directory at startup so the next process doesn't
        accumulate them indefinitely — a container restart loop would fill
        the filesystem otherwise."""
        if not self.temp_dir.exists():
            return
        swept = 0
        for png in self.temp_dir.glob("*.png"):
            try:
                png.unlink()
                swept += 1
            except OSError as error:
                logger.debug("Could not sweep stale OCR temp file %s: %s", png, error)
        if swept:
            logger.info("OCR temp-dir sweep removed %s stale file(s)", swept)

    async def extract_text(self, upload: ImageUpload) -> str:
        validate_image_upload(upload, max_file_size=self.max_file_size)

        self.temp_dir.mkdir(parents=True, exist_ok=True)
        processed_path = self.temp_dir / f"{uuid4().hex}.png"
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._preprocess, upload.content, processed_path),
                timeout=self.timeout,
            )
            text = await asyncio.wait_for(
                loop.run_in_executor(None, self._ocr, processed_path),
                timeout=self.timeout,
            )
        except TimeoutError as error:
            raise ValidationError("errors.ocr_timeout") from error
        except UnidentifiedImageError as error:
            raise ValidationError("errors.broken_image") from error
        finally:
            try:
                processed_path.unlink(missing_ok=True)
            except OSError as error:
                logger.warning("Failed to remove OCR temp file %s: %s", processed_path, error)

        cleaned = text.strip()
        if not cleaned:
            raise ValidationError("errors.ocr_empty")
        return cleaned

    @staticmethod
    def _preprocess(source_content: bytes, target_path: Path) -> None:
        with Image.open(BytesIO(source_content)) as image:
            width, height = image.size
            # LANCZOS keeps letter edges sharp at 2× upscale; the old default
            # (BILINEAR) rounded serifs and made small Cyrillic % signs mushy.
            resized = image.resize(
                (max(1, width * 2), max(1, height * 2)),
                resample=Image.Resampling.LANCZOS,
            )
            grayscale = resized.convert("L")
            # Modern bank apps default to dark themes — light text on near-black
            # backgrounds. Tesseract is trained on dark-text-on-light, so we
            # invert when the mean brightness indicates a dark-dominant image.
            # The threshold (~96) is empirically safe: neutral/light screens
            # (mean 140+) pass through untouched.
            grayscale = _autoinvert_if_dark(grayscale, threshold=96)
            contrasted = ImageOps.autocontrast(grayscale, cutoff=2)
            # UnsharpMask produces a visibly crisper glyph edge than the plain
            # SHARPEN kernel — especially for thin Cyrillic strokes at small
            # sizes. Threshold=3 ignores the tiny noise the autocontrast step
            # would otherwise amplify.
            sharpened = contrasted.filter(ImageFilter.UnsharpMask(radius=1.5, percent=180, threshold=3))
            denoised = sharpened.filter(ImageFilter.MedianFilter(size=3))
            denoised.save(target_path, format="PNG")

    @staticmethod
    def _ocr(processed_path: Path) -> str:
        with Image.open(processed_path) as image:
            return pytesseract.image_to_string(
                image,
                lang="rus+eng",
                config="--oem 3 --psm 6 -c preserve_interword_spaces=1",
            )


def _autoinvert_if_dark(grayscale: Image.Image, *, threshold: int) -> Image.Image:
    # Sample a reduced copy so "mean brightness" doesn't scan the full image
    # for every photo — costs ~1 ms vs ~30 ms for large screenshots.
    thumb = grayscale.resize((64, 64))
    stats = ImageStat.Stat(thumb)
    mean = stats.mean[0] if stats.mean else 0.0
    if mean < threshold:
        return ImageOps.invert(grayscale)
    return grayscale
