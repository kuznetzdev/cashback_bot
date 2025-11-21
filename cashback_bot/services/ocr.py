from __future__ import annotations

"""OCR service with preprocessing and fallback attempts."""
import asyncio
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image
import pytesseract

from .preprocessing import PreprocessingService

LOGGER = logging.getLogger(__name__)


class OCRService:
    def __init__(
        self,
        temp_dir: Path,
        *,
        workers: int = 2,
        primary_lang: str = "rus+eng",
        secondary_lang: str = "eng",
    ) -> None:
        self._temp_dir = temp_dir
        self._pre = PreprocessingService()
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ocr")
        self._primary_lang = primary_lang
        self._secondary_lang = secondary_lang
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    async def read_text(self, image_bytes: bytes, timeout: float = 18.0) -> Optional[str]:
        loop = asyncio.get_running_loop()
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._temp_dir, suffix=".png")
        with open(tmp_fd, "wb") as file:  # type: ignore[arg-type]
            file.write(image_bytes)

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, self._perform_ocr, Path(tmp_path)),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            LOGGER.warning("OCR timed out after %.2f seconds", timeout)
            return None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _perform_ocr(self, path: Path) -> Optional[str]:
        image = cv2.imread(str(path))
        if image is None:
            LOGGER.error("Could not read image %s", path)
            return None

        cleaned = self._pre.normalize(image)
        text = self._extract_text(cleaned, lang=self._primary_lang)
        if not text:
            LOGGER.debug("Primary OCR empty, retrying with alternate threshold")
            alt = self._pre.adaptive_binarize(self._pre.to_grayscale(image), block_size=21, c=2)
            text = self._extract_text(alt, lang=self._secondary_lang)
        normalized = self._postprocess(text or "")
        return normalized or None

    def _extract_text(self, image: np.ndarray, lang: str) -> str:
        pil_image = Image.fromarray(image)
        return pytesseract.image_to_string(pil_image, lang=lang)

    def _postprocess(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            cleaned = cleaned.replace("АЗC", "АЗС").replace("азc", "азс")
            cleaned = cleaned.replace("%", " %")
            if len(cleaned) > 80:
                cleaned = cleaned[:80]
            if cleaned.replace(" ", "").isalnum():
                continue
            lines.append(cleaned)
        unique_lines = []
        seen = set()
        for line in lines:
            if line not in seen:
                unique_lines.append(line)
                seen.add(line)
        return "\n".join(unique_lines)

    async def close(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._executor.shutdown, True)
