"""OCR service with preprocessing and timeout support."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter
import pytesseract

LOGGER = logging.getLogger(__name__)


class OCRService:
    """Perform OCR with light preprocessing on user-provided images."""

    def __init__(self, temp_dir: Path, workers: int = 2) -> None:
        self._temp_dir = temp_dir
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ocr")
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    async def read_text(self, image_bytes: bytes, timeout: float = 12.0) -> Optional[str]:
        loop = asyncio.get_running_loop()
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._temp_dir, suffix=".png")
        with os.fdopen(tmp_fd, "wb") as file:
            file.write(image_bytes)

        try:
            LOGGER.debug("Running OCR for %s", tmp_path)
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, self._perform_ocr, Path(tmp_path)),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            LOGGER.warning("OCR timed out after %.2f seconds", timeout)
            return None
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                LOGGER.exception("Failed to cleanup OCR temp file: %s", tmp_path)

    def _perform_ocr(self, path: Path) -> Optional[str]:
        try:
            with Image.open(path) as image:
                grayscale = image.convert("L")
                sharpened = grayscale.filter(ImageFilter.SHARPEN)
                thresholded = sharpened.point(lambda p: 255 if p > 140 else 0)
                text = pytesseract.image_to_string(thresholded, lang="rus+eng")
                return text.strip() or None
        except Exception:  # pylint: disable=broad-except
            LOGGER.exception("OCR failed for %s", path)
            return None

    async def close(self) -> None:
        LOGGER.info("Shutting down OCR executor")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._executor.shutdown, True)

