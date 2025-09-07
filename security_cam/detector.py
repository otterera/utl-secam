"""Human detection using OpenCV HOG and lightweight NMS.

This module defines a small detection result dataclass, a NumPy-based NMS,
and a `HumanDetector` that wraps OpenCV’s default people detector.
"""

from dataclasses import dataclass  # For structured detection results
from typing import List, Tuple, Any  # Type hints
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


class _CascadeFaceDetector:
    """Base for Haar/LBP detectors with shared loader and preprocessing."""

    def __init__(self, filenames: List[str]) -> None:
        self.cascade = None
        candidates = []
        try:
            candidates.extend([os.path.join(cv2.data.haarcascades, f) for f in filenames])  # type: ignore[attr-defined]
        except Exception:
            pass
        candidates.extend([
            "/usr/share/opencv4/haarcascades/",
            "/usr/share/opencv/haarcascades/",
            "/usr/local/share/opencv4/haarcascades/",
        ])
        files: List[str] = []
        for base in candidates:
            if base.endswith(".xml"):
                files.append(base)
            else:
                files.extend([os.path.join(base, f) for f in filenames])
        for path in files:
            if os.path.exists(path):
                c = cv2.CascadeClassifier(path)
                if not c.empty():
                    self.cascade = c
                    break

    def _preproc(self, frame_bgr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if Config.FACE_USE_CLAHE:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
        return gray

    def detect(self, frame_bgr: np.ndarray) -> List[Detection]:
        if self.cascade is None:
            return []
        gray = self._preproc(frame_bgr)
        # Dynamic min size based on frame size
        h, w = gray.shape[:2]
        min_side = int(min(h, w) * max(0.0, min(1.0, Config.FACE_MIN_SIZE_FRAC)))
        min_side = max(min_side, Config.FACE_MIN_SIZE)
        faces = self.cascade.detectMultiScale(
            gray,
            scaleFactor=Config.FACE_SCALE_FACTOR,
            minNeighbors=Config.FACE_MIN_NEIGHBORS,
            flags=cv2.CASCADE_SCALE_IMAGE,
            minSize=(min_side, min_side),
        )
        return [Detection((int(x), int(y), int(w), int(h)), 1.0, "face") for (x, y, w, h) in faces]


class HaarFaceDetector(_CascadeFaceDetector):
    def __init__(self) -> None:
        super().__init__(["haarcascade_frontalface_default.xml"])


class LbpFaceDetector(_CascadeFaceDetector):
    def __init__(self) -> None:
        super().__init__(["lbpcascade_frontalface.xml"])


## DnnFaceDetector removed (DNN approach not used on Pi 3B)


class MultiHumanDetector:
    """Composite detector: HOG person + Haar face.

    Triggers if either a person or a face is detected. Overlapping boxes are
    reduced via NMS.
    """

    def __init__(self) -> None:
        self.person = HumanDetector()
        self.face = None
        if Config.USE_FACE_DETECT:
            backend = Config.FACE_BACKEND
            if backend == "lbp":
                self.face = LbpFaceDetector()
            else:
                self.face = HaarFaceDetector()

    def detect(
        self,
        frame_bgr: np.ndarray,
        *,
        hit_threshold: float | None = None,
        min_size: Tuple[int, int] | None = None,
        **_: Any,
    ) -> List[Detection]:
        """Run combined person + face detection and merge results.

        Accepts and forwards optional thresholds to the HOG person detector.
        """
        results: List[Detection] = []
        # Person detection (HOG); forward dynamic params if provided
        try:
            results.extend(self.person.detect(
                frame_bgr,
                hit_threshold=hit_threshold,
                min_size=min_size,
            ))
        except Exception:
            # Be defensive; continue with face detection if HOG fails
            pass
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


class MotionDetector:
    """Simple frame-difference motion detector for recall-first detection.

    Maintains the previous grayscale, blurred frame (optionally downscaled), and
    triggers a positive result when the number of changed pixels exceeds a
    threshold. Returns one or more bounding boxes for changed regions.
    """

    def __init__(self) -> None:
        self.prev: np.ndarray | None = None

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
        _, thresh = cv2.threshold(diff, int(Config.MOTION_DELTA_THRESH), 255, cv2.THRESH_BINARY)
        dilate_iter = max(0, int(Config.MOTION_DILATE_ITER))
        if dilate_iter:
            thresh = cv2.dilate(thresh, None, iterations=dilate_iter)
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


def get_detector(backend: str):
    """Factory returning a detector instance based on backend name."""
    b = (backend or "").strip().lower()
    if b == "motion":
        return MotionDetector()
    if b in ("bg", "bgsub", "mog2", "knn"):
        method = "knn" if b == "knn" else (Config.BG_METHOD if b in ("bg", "bgsub") else b)
        return BackgroundSubtractorDetector(method=method)
    return MultiHumanDetector()


class BackgroundSubtractorDetector:
    """Background subtraction (MOG2/KNN) motion/object detector.

    Uses OpenCV's background subtractors to obtain a foreground mask and then
    extracts bounding boxes of moving regions via contours.
    """

    def __init__(self, method: str = "mog2") -> None:
        m = (method or "mog2").strip().lower()
        if m == "knn":
            self.bg = cv2.createBackgroundSubtractorKNN(history=int(Config.BG_HISTORY), detectShadows=bool(Config.BG_DETECT_SHADOWS))
        else:
            self.bg = cv2.createBackgroundSubtractorMOG2(history=int(Config.BG_HISTORY), varThreshold=float(Config.BG_VAR_THRESHOLD), detectShadows=bool(Config.BG_DETECT_SHADOWS))

    def _prep(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        scale = float(max(0.1, min(1.0, Config.BG_DOWNSCALE)))
        small = frame_bgr
        if scale != 1.0:
            small = cv2.resize(frame_bgr, (int(frame_bgr.shape[1] * scale), int(frame_bgr.shape[0] * scale)))
        k = max(1, int(Config.BG_BLUR_KERNEL) | 1)
        if k > 1:
            small = cv2.GaussianBlur(small, (k, k), 0)
        return small, scale

    def detect(self, frame_bgr: np.ndarray, **_: Any) -> List[Detection]:
        small, scale = self._prep(frame_bgr)
        lr = float(Config.BG_LEARNING_RATE)
        fgmask = self.bg.apply(small, learningRate=lr)
        # Remove shadows (127) if shadow detection is on; keep only 255
        if Config.BG_DETECT_SHADOWS:
            _, fgmask = cv2.threshold(fgmask, 250, 255, cv2.THRESH_BINARY)
        # Morphology to close gaps
        it = max(0, int(Config.BG_DILATE_ITER))
        if it:
            fgmask = cv2.dilate(fgmask, None, iterations=it)
        # Count changed pixels
        changed = int(cv2.countNonZero(fgmask))
        if changed < int(Config.BG_MIN_PIXELS):
            return []
        # Contours to boxes
        contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dets: List[Detection] = []
        for c in contours:
            if cv2.contourArea(c) < Config.BG_MIN_PIXELS:
                continue
            x, y, w, h = cv2.boundingRect(c)
            if scale != 1.0:
                x = int(x / scale)
                y = int(y / scale)
                w = int(w / scale)
                h = int(h / scale)
            dets.append(Detection((x, y, w, h), 1.0, "bg"))
        if not dets:
            # Fallback to full-frame if mask says motion but contours are tiny
            h0, w0 = frame_bgr.shape[:2]
            dets.append(Detection((0, 0, w0, h0), 1.0, "bg"))
        return dets
