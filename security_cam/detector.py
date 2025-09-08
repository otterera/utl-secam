"""Motion-only detector (frame differencing).

Defines `Detection` and a `MotionDetector` that triggers when consecutive frames
change beyond a configured threshold. All other detector types have been
removed for simplicity and performance on the Raspberry Pi 3B.
"""

from dataclasses import dataclass  # For structured detection results
from typing import Any, List, Tuple  # Type hints

import cv2  # OpenCV
import numpy as np  # Arrays

from .config import Config  # Tunable detector parameters


@dataclass
class Detection:
    """Represents a single detection result.

    Attributes:
      bbox: (x, y, w, h) bounding box in image coordinates.
      score: Detector score (use 1.0 for motion).
      kind: Label of detector type, e.g., 'motion'.
    """

    bbox: Tuple[int, int, int, int]
    score: float
    kind: str


class MotionDetector:
    """Simple frame-difference motion detector for recall-first detection.

    Maintains the previous grayscale, blurred frame (optionally downscaled), and
    triggers a positive result when the number of changed pixels exceeds a
    threshold. Returns one or more bounding boxes for changed regions.
    """

    def __init__(self) -> None:
        self.prev: np.ndarray | None = None
        # Optional static mask path from config; loaded lazily and resized per scale
        self._mask_path = Config.MOTION_MASK_PATH
        self._mask_cached_scale: float | None = None
        self._mask_scaled: np.ndarray | None = None

    def reset(self) -> None:
        """Reset the motion baseline so the next frame seeds it without detecting.

        Use this when camera parameters (exposure/gain/shutter) change so that
        detection does not trigger on global brightness jumps unrelated to real
        motion.
        """
        self.prev = None

    def seed(self, frame_bgr: np.ndarray) -> None:
        """Seed the baseline using the given frame, without producing detections.

        This prepares `prev` to the preprocessed (grayscale/blurred/downscaled)
        version of `frame_bgr`, so that the next call to `detect()` compares
        against this snapshot instead of an older baseline.
        """
        cur, _ = self._prep(frame_bgr)
        self.prev = cur

    def _prep(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        scale = float(max(0.1, min(1.0, Config.MOTION_DOWNSCALE)))
        if scale != 1.0:
            gray = cv2.resize(gray, (int(gray.shape[1] * scale), int(gray.shape[0] * scale)))
        k = max(1, int(Config.MOTION_BLUR_KERNEL) | 1)  # ensure odd
        gray = cv2.GaussianBlur(gray, (k, k), 0)
        return gray, scale

    def detect(self, frame_bgr: np.ndarray, **_: Any) -> List[Detection]:
        cur, scale = self._prep(frame_bgr)
        if self.prev is None:
            self.prev = cur
            return []
        diff = cv2.absdiff(self.prev, cur)
        self.prev = cur
        # Noise-adaptive thresholding: base + K * sigma over a small center ROI
        base_thresh = int(Config.MOTION_DELTA_THRESH)
        if Config.MOTION_NOISE_ADAPT:
            h, w = diff.shape[:2]
            rf = max(0.05, min(0.9, float(Config.MOTION_NOISE_ROI_FRAC)))
            cx1 = int(w * (0.5 - rf / 2))
            cy1 = int(h * (0.5 - rf / 2))
            cx2 = int(w * (0.5 + rf / 2))
            cy2 = int(h * (0.5 + rf / 2))
            roi = diff[cy1:cy2, cx1:cx2]
            try:
                sigma = float(roi.std()) if roi.size else 0.0
            except Exception:
                sigma = 0.0
            base_thresh = min(255, max(0, int(base_thresh + float(Config.MOTION_NOISE_K) * sigma)))
        _, thresh = cv2.threshold(diff, base_thresh, 255, cv2.THRESH_BINARY)
        dilate_iter = max(0, int(Config.MOTION_DILATE_ITER))
        if dilate_iter:
            thresh = cv2.dilate(thresh, None, iterations=dilate_iter)
        # Optional morphological opening to remove speckles
        open_iter = max(0, int(Config.MOTION_OPEN_ITER))
        if open_iter:
            kernel = np.ones((3, 3), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=open_iter)
        # Apply static mask if provided (black=ignore, white=keep)
        if self._mask_path:
            try:
                if self._mask_scaled is None or self._mask_cached_scale != scale:
                    mask = cv2.imread(self._mask_path, cv2.IMREAD_GRAYSCALE)
                    if mask is not None:
                        # Resize mask to current working size
                        mh, mw = cur.shape[:2]
                        mask_r = cv2.resize(mask, (mw, mh), interpolation=cv2.INTER_NEAREST)
                        # Binarize
                        _, mask_b = cv2.threshold(mask_r, 127, 255, cv2.THRESH_BINARY)
                        self._mask_scaled = mask_b
                        self._mask_cached_scale = scale
                if self._mask_scaled is not None:
                    thresh = cv2.bitwise_and(thresh, self._mask_scaled)
            except Exception:
                pass
        changed_pixels = int(cv2.countNonZero(thresh))
        if changed_pixels < int(Config.MOTION_MIN_PIXELS):
            return []
        # Find contours and build bounding boxes
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: List[Detection] = []
        for c in contours:
            if cv2.contourArea(c) < Config.MOTION_MIN_PIXELS:
                continue
            x, y, w, h = cv2.boundingRect(c)
            # Rescale to original frame coordinates
            if scale != 1.0:
                x = int(x / scale)
                y = int(y / scale)
                w = int(w / scale)
                h = int(h / scale)
            detections.append(Detection((x, y, w, h), 1.0, "motion"))
        # If no sizable contours, still signal motion by a full-frame box
        if not detections:
            h0, w0 = frame_bgr.shape[:2]
            detections.append(Detection((0, 0, w0, h0), 1.0, "motion"))
        return detections
