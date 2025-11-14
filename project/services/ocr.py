"""OCR service with advanced preprocessing and dual-language support."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image
import pytesseract

LOGGER = logging.getLogger(__name__)


class OCRService:
    """Perform OCR with aggressive preprocessing for banking tables."""

    def __init__(
        self,
        temp_dir: Path,
        workers: int = 2,
        primary_lang: str = "rus+eng",
        secondary_lang: str = "eng",
    ) -> None:
        self._temp_dir = temp_dir
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ocr")
        self._primary_lang = primary_lang
        self._secondary_lang = secondary_lang
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
            image = cv2.imread(str(path))
            if image is None:
                LOGGER.error("Failed to read image for OCR: %s", path)
                return None
            processed = self._preprocess_image(image)
            pil_image = Image.fromarray(processed)
            primary_text = pytesseract.image_to_string(pil_image, lang=self._primary_lang)
            secondary_text = ""
            if self._secondary_lang and self._secondary_lang != self._primary_lang:
                secondary_text = pytesseract.image_to_string(pil_image, lang=self._secondary_lang)
            merged = self._merge_text(primary_text, secondary_text)
            return merged or None
        except Exception:  # pylint: disable=broad-except
            LOGGER.exception("OCR failed for %s", path)
            return None

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        denoised = cv2.bilateralFilter(grayscale, 9, 75, 75)
        equalized = cv2.equalizeHist(denoised)
        binary = cv2.adaptiveThreshold(
            equalized,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            2,
        )
        table_mask = self._extract_table_mask(binary)
        enhanced = cv2.bitwise_and(binary, table_mask)
        cropped = self._auto_crop(enhanced)
        return cropped

    def _auto_crop(self, image: np.ndarray) -> np.ndarray:
        inverted = cv2.bitwise_not(image)
        coords = cv2.findNonZero(inverted)
        if coords is None:
            return image
        x, y, w, h = cv2.boundingRect(coords)
        if w < 20 or h < 20:
            return image
        return image[y : y + h, x : x + w]

    def _extract_table_mask(self, image: np.ndarray) -> np.ndarray:
        horizontal_kernel_size = max(1, image.shape[1] // 40)
        vertical_kernel_size = max(1, image.shape[0] // 40)
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_kernel_size, 1))
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_kernel_size))
        horizontal = cv2.erode(image, horizontal_kernel, iterations=1)
        horizontal = cv2.dilate(horizontal, horizontal_kernel, iterations=1)
        vertical = cv2.erode(image, vertical_kernel, iterations=1)
        vertical = cv2.dilate(vertical, vertical_kernel, iterations=1)
        table = cv2.bitwise_or(horizontal, vertical)
        return cv2.bitwise_not(table)

    def _merge_text(self, primary: str, secondary: str) -> str:
        lines = {line.strip() for line in primary.splitlines() if line.strip()}
        for line in secondary.splitlines():
            cleaned = line.strip()
            if cleaned:
                lines.add(cleaned)
        return "\n".join(sorted(lines))

    async def close(self) -> None:
        LOGGER.info("Shutting down OCR executor")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._executor.shutdown, True)

