from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
import pytesseract

from app.config import Settings
from app.core.exceptions import FileTooLargeError, ImageProcessingError, OCREmptyError, OCRTimeoutError
from app.utils.executor import run_blocking


class OCRService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_path

    async def extract_text(self, image_path: Path) -> str:
        if image_path.stat().st_size > self.settings.max_file_size:
            raise FileTooLargeError(self.settings.max_file_size)

        try:
            text = await run_blocking(self._extract_sync, image_path, timeout=self.settings.ocr_timeout)
        except TimeoutError as error:
            raise OCRTimeoutError() from error
        except UnidentifiedImageError as error:
            raise ImageProcessingError() from error

        cleaned = text.strip()
        if not cleaned:
            raise OCREmptyError()
        return cleaned

    def _extract_sync(self, image_path: Path) -> str:
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            image.thumbnail((2200, 2200))
            image = ImageOps.grayscale(image)
            image = image.filter(ImageFilter.MedianFilter(size=3))
            image = image.filter(ImageFilter.SHARPEN)
            image = image.point(lambda pixel: 255 if pixel > 160 else 0)
            return pytesseract.image_to_string(image, lang="rus+eng", config="--oem 3 --psm 6")
