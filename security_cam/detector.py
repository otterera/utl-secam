from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

from .config import Config


@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    score: float


class HumanDetector:
    def __init__(self) -> None:
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame_bgr: np.ndarray) -> List[Detection]:
        # Work on a smaller copy for speed
        h, w = frame_bgr.shape[:2]
        scale_for_speed = 0.75 if max(h, w) > 640 else 1.0
        if scale_for_speed != 1.0:
            small = cv2.resize(frame_bgr, (int(w * scale_for_speed), int(h * scale_for_speed)))
        else:
            small = frame_bgr

        rects, weights = self.hog.detectMultiScale(
            small,
            winStride=(Config.DETECTOR_STRIDE, Config.DETECTOR_STRIDE),
            padding=(8, 8),
            scale=Config.DETECTOR_SCALE,
            hitThreshold=Config.DETECTOR_HIT_THRESHOLD,
        )

        detections: List[Detection] = []
        for (x, y, w0, h0), score in zip(rects, weights):
            # Rescale bbox back to original frame size
            if scale_for_speed != 1.0:
                x = int(x / scale_for_speed)
                y = int(y / scale_for_speed)
                w0 = int(w0 / scale_for_speed)
                h0 = int(h0 / scale_for_speed)
            if w0 < Config.DETECTOR_MIN_WIDTH or h0 < Config.DETECTOR_MIN_HEIGHT:
                continue
            detections.append(Detection((x, y, w0, h0), float(score)))

        # Non-maximum suppression to reduce overlapping boxes
        if detections:
            boxes = np.array([(*d.bbox,) for d in detections]).astype(np.float32)
            scores = np.array([d.score for d in detections]).astype(np.float32)
            idxs = cv2.dnn.NMSBoxesBatched(
                [boxes.tolist()], [scores.tolist()], score_threshold=0.0, nms_threshold=0.4
            )
            # idxs is a list of lists per batch; we have a single batch
            keep = set(int(i) for i in (idxs[0] if len(idxs) > 0 else []))
            detections = [d for i, d in enumerate(detections) if i in keep] or detections
        return detections

