from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

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

    async def extract_text(self, upload: ImageUpload) -> str:
        if not upload.content:
            raise ValidationError("errors.broken_image")
        if len(upload.content) > self.max_file_size:
            raise ValidationError("errors.file_too_large")

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
            resized = image.resize((max(1, width * 2), max(1, height * 2)))
            grayscale = resized.convert("L")
            contrasted = ImageOps.autocontrast(grayscale, cutoff=2)
            enhanced = ImageEnhance.Contrast(contrasted).enhance(1.4)
            sharpened = enhanced.filter(ImageFilter.SHARPEN)
            denoised = grayscale.filter(ImageFilter.MedianFilter(size=3))
            thresholded = denoised.point(lambda pixel: 255 if pixel > 145 else 0)
            thresholded = ImageOps.autocontrast(thresholded)
            thresholded = thresholded.filter(ImageFilter.MedianFilter(size=3))
            thresholded = Image.blend(sharpened, thresholded, alpha=0.7)
            thresholded.save(target_path, format="PNG")

    @staticmethod
    def _ocr(processed_path: Path) -> str:
        with Image.open(processed_path) as image:
            return pytesseract.image_to_string(
                image,
                lang="rus+eng",
                config="--oem 3 --psm 6 -c preserve_interword_spaces=1",
            )
