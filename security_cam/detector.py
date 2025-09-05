from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

from .config import Config


@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    score: float


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.4) -> List[int]:
    """Pure-python/Numpy NMS for [x, y, w, h] boxes; returns kept indices."""
    if len(boxes) == 0:
        return []
    # convert to x1,y1,x2,y2
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 0] + boxes[:, 2]
    y2 = boxes[:, 1] + boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: List[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(iou <= iou_thresh)[0]
        order = order[inds + 1]
    return keep


class HumanDetector:
    def __init__(self) -> None:
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(
        self,
        frame_bgr: np.ndarray,
        *,
        hit_threshold: float | None = None,
        min_size: Tuple[int, int] | None = None,
    ) -> List[Detection]:
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
            hitThreshold=(Config.DETECTOR_HIT_THRESHOLD if hit_threshold is None else hit_threshold),
        )

        detections: List[Detection] = []
        for (x, y, w0, h0), score in zip(rects, weights):
            # Rescale bbox back to original frame size
            if scale_for_speed != 1.0:
                x = int(x / scale_for_speed)
                y = int(y / scale_for_speed)
                w0 = int(w0 / scale_for_speed)
                h0 = int(h0 / scale_for_speed)
            min_w = Config.DETECTOR_MIN_WIDTH if min_size is None else int(min_size[0])
            min_h = Config.DETECTOR_MIN_HEIGHT if min_size is None else int(min_size[1])
            if w0 < min_w or h0 < min_h:
                continue
            detections.append(Detection((x, y, w0, h0), float(score)))

        # Non-maximum suppression to reduce overlapping boxes
        if detections:
            boxes = np.array([(*d.bbox,) for d in detections]).astype(np.float32)
            scores = np.array([d.score for d in detections]).astype(np.float32)
            keep = _nms(boxes, scores, iou_thresh=0.4)
            detections = [d for i, d in enumerate(detections) if i in keep]
        return detections
