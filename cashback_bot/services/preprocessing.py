from __future__ import annotations

"""Image preprocessing helpers used by OCR pipeline."""
import cv2
import numpy as np


class PreprocessingService:
    def to_grayscale(self, image: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def denoise(self, image: np.ndarray) -> np.ndarray:
        return cv2.fastNlMeansDenoising(image, None, h=10, templateWindowSize=7, searchWindowSize=21)

    def adaptive_binarize(self, image: np.ndarray, *, block_size: int = 31, c: int = 5) -> np.ndarray:
        block_size = block_size if block_size % 2 == 1 else block_size + 1
        return cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c)

    def remove_small_artifacts(self, binary: np.ndarray, min_area: int = 40) -> np.ndarray:
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask = np.zeros_like(binary)
        for contour in contours:
            if cv2.contourArea(contour) >= min_area:
                cv2.drawContours(mask, [contour], -1, 255, -1)
        return cv2.bitwise_and(binary, mask)

    def normalize(self, image: np.ndarray) -> np.ndarray:
        grayscale = self.to_grayscale(image)
        denoised = self.denoise(grayscale)
        binarized = self.adaptive_binarize(denoised)
        cleaned = self.remove_small_artifacts(binarized)
        return cleaned
