"""Human detection using OpenCV HOG and lightweight NMS.

This module defines a small detection result dataclass, a NumPy-based NMS,
and a `HumanDetector` that wraps OpenCV’s default people detector.
"""

from dataclasses import dataclass  # For structured detection results
from typing import List, Tuple  # Type hints
import os  # For file existence checks

import cv2  # OpenCV for HOG person detection
import numpy as np  # Arrays and vectorized NMS

from .config import Config  # Tunable detector parameters


@dataclass
class Detection:
    """Represents a single detection result.

    Attributes:
      bbox: (x, y, w, h) bounding box in image coordinates.
      score: Detector confidence score (if available).
      kind: Label of detector type, e.g., 'person' or 'face'.
    """

    bbox: Tuple[int, int, int, int]  # x, y, w, h
    score: float  # Detector score
    kind: str  # e.g., 'person' or 'face'


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.4) -> List[int]:
    """Perform Non-Maximum Suppression on [x, y, w, h] boxes.

    Pure NumPy implementation to avoid relying on OpenCV DNN helpers that may
    be missing in older Raspberry Pi builds.

    Args:
      boxes: Array of shape (N, 4) with [x, y, w, h].
      scores: Array of shape (N,) with detection scores.
      iou_thresh: IOU threshold for suppression.

    Returns:
      List of indices of boxes to keep.
    """
    if len(boxes) == 0:  # No boxes to process
        return []
    # Convert to corner coordinates for IoU computation
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 0] + boxes[:, 2]
    y2 = boxes[:, 1] + boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)  # Box areas
    order = scores.argsort()[::-1]  # Process highest score first
    keep: List[int] = []  # Indices to retain
    while order.size > 0:
        i = int(order[0])  # Index with highest score
        keep.append(i)  # Keep it
        if order.size == 1:  # Nothing else to compare
            break
        # Compute overlap with the rest
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h  # Intersection area
        iou = inter / (areas[i] + areas[order[1:]] - inter)  # IoU vector
        inds = np.where(iou <= iou_thresh)[0]  # Keep those with IoU below thresh
        order = order[inds + 1]  # Advance to remaining indices
    return keep


class HumanDetector:
    """HOG-based pedestrian detector with optional dynamic thresholds."""

    def __init__(self) -> None:
        """Initialize HOG descriptor with the default people SVM."""
        self.hog = cv2.HOGDescriptor()  # Create HOG descriptor
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())  # Load default SVM

    def detect(
        self,
        frame_bgr: np.ndarray,
        *,
        hit_threshold: float | None = None,
        min_size: Tuple[int, int] | None = None,
    ) -> List[Detection]:
        """Run HOG person detection on a BGR frame.

        Args:
          frame_bgr: Input frame in BGR order.
          hit_threshold: Optional SVM hit threshold override.
          min_size: Optional minimum box size `(min_w, min_h)` override.

        Returns:
          A list of `Detection` objects after non-maximum suppression.
        """
        # Optionally work on a smaller copy for speed
        h, w = frame_bgr.shape[:2]  # Frame dimensions
        scale_for_speed = 0.75 if max(h, w) > 640 else 1.0  # Scale large frames
        if scale_for_speed != 1.0:
            # Resize frame while preserving aspect ratio
            small = cv2.resize(frame_bgr, (int(w * scale_for_speed), int(h * scale_for_speed)))
        else:
            small = frame_bgr  # Use original frame

        # Run HOG detection
        rects, weights = self.hog.detectMultiScale(
            small,  # Possibly downscaled frame
            winStride=(Config.DETECTOR_STRIDE, Config.DETECTOR_STRIDE),  # Step size
            padding=(8, 8),  # Padding around detection window
            scale=Config.DETECTOR_SCALE,  # Image pyramid scale
            hitThreshold=(Config.DETECTOR_HIT_THRESHOLD if hit_threshold is None else hit_threshold),  # SVM thresh
        )

        detections: List[Detection] = []  # Collected detections
        for (x, y, w0, h0), score in zip(rects, weights):  # Iterate boxes/scores
            # Rescale bbox back to original frame size if we downscaled
            if scale_for_speed != 1.0:
                x = int(x / scale_for_speed)
                y = int(y / scale_for_speed)
                w0 = int(w0 / scale_for_speed)
                h0 = int(h0 / scale_for_speed)
            # Enforce minimum size thresholds
            min_w = Config.DETECTOR_MIN_WIDTH if min_size is None else int(min_size[0])
            min_h = Config.DETECTOR_MIN_HEIGHT if min_size is None else int(min_size[1])
            if w0 < min_w or h0 < min_h:
                continue  # Skip tiny boxes
            detections.append(Detection((x, y, w0, h0), float(score), "person"))  # Add result

        # Non-maximum suppression to reduce overlapping boxes
        if detections:
            boxes = np.array([(*d.bbox,) for d in detections]).astype(np.float32)  # Nx4 boxes
            scores = np.array([d.score for d in detections]).astype(np.float32)  # N scores
            keep = _nms(boxes, scores, iou_thresh=0.4)  # Indices to keep
            detections = [d for i, d in enumerate(detections) if i in keep]  # Filtered list
        return detections  # Final detections


class FaceDetector:
    """Haar cascade face detector as a complementary signal."""

    def __init__(self) -> None:
        """Load OpenCV Haar cascade for frontal faces."""
        self.cascade = None
        # Try several candidate locations; load only if the file exists
        candidates = []
        try:
            candidates.append(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))  # type: ignore[attr-defined]
        except Exception:
            pass
        candidates.extend([
            "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
            "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
            "/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        ])
        for path in candidates:
            if os.path.exists(path):
                c = cv2.CascadeClassifier(path)
                if not c.empty():
                    self.cascade = c
                    break

    def detect(self, frame_bgr: np.ndarray) -> List[Detection]:
        """Detect frontal faces and return as Detection list."""
        if self.cascade is None:
            return []
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.cascade.detectMultiScale(
            gray,
            scaleFactor=Config.FACE_SCALE_FACTOR,
            minNeighbors=Config.FACE_MIN_NEIGHBORS,
            flags=cv2.CASCADE_SCALE_IMAGE,
            minSize=(Config.FACE_MIN_SIZE, Config.FACE_MIN_SIZE),
        )
        detections: List[Detection] = []
        for (x, y, w, h) in faces:
            detections.append(Detection((int(x), int(y), int(w), int(h)), 1.0, "face"))
        return detections


class MultiHumanDetector:
    """Composite detector: HOG person + Haar face.

    Triggers if either a person or a face is detected. Overlapping boxes are
    reduced via NMS.
    """

    def __init__(self) -> None:
        self.person = HumanDetector()
        self.face = FaceDetector() if Config.USE_FACE_DETECT else None

    def detect(
        self,
        frame_bgr: np.ndarray,
        *,
        hit_threshold: float | None = None,
        min_size: Tuple[int, int] | None = None,
    ) -> List[Detection]:
        """Run combined person + face detection and merge results."""
        results: List[Detection] = []
        # Person detection (HOG)
        results.extend(self.person.detect(frame_bgr))
        # Face detection (Haar)
        if self.face is not None:
            try:
                results.extend(self.face.detect(frame_bgr))
            except Exception:
                pass
        if not results:
            return []
        # NMS across mixed detections using their scores
        boxes = np.array([(*d.bbox,) for d in results]).astype(np.float32)
        scores = np.array([d.score for d in results]).astype(np.float32)
        keep = _nms(boxes, scores, iou_thresh=0.4)
        return [d for i, d in enumerate(results) if i in keep]
