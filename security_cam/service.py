import os
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

from .camera import BaseCamera, make_camera
from .config import Config
from .detector import HumanDetector
from .schedule import DailySchedule


@dataclass
class ServiceState:
    detecting: bool = False
    last_detection_ts: float = 0.0
    saved_images_count: int = 0
    total_frames: int = 0
    armed: bool = True


class SecurityCamService:
    def __init__(self) -> None:
        self.config = Config
        self.camera: BaseCamera = make_camera()
        self.detector = HumanDetector()
        self.state = ServiceState()
        self.schedule = DailySchedule(self.config.ACTIVE_WINDOWS)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._last_saved_ts: float = 0.0
        os.makedirs(self.config.SAVE_DIR, exist_ok=True)

    # Public API
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.camera.stop()

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def get_status(self) -> ServiceState:
        return self.state

    def list_latest_images(self, limit: int) -> List[str]:
        try:
            files = [
                os.path.join(self.config.SAVE_DIR, f)
                for f in os.listdir(self.config.SAVE_DIR)
                if f.lower().endswith(".jpg")
            ]
        except FileNotFoundError:
            return []
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return files[:limit]

    # Internal
    def _run(self) -> None:
        frame_idx = 0
        interval = 1.0 / max(1, self.config.CAPTURE_FPS)
        # Initialize camera here so Flask can start even if camera blocks
        started = False
        while not self._stop.is_set():
            if not started:
                try:
                    self.camera.start()
                    print("[secam] Camera started (backend=%s)" % self.config.CAMERA_BACKEND, flush=True)
                    started = True
                except Exception as e:
                    print(f"[secam] Camera start failed: {e}", flush=True)
                    time.sleep(3.0)
                    continue
            frame = self.camera.read()
            if frame is None:
                time.sleep(0.01)
                continue

            # store latest
            with self._frame_lock:
                self._latest_frame = frame
            self.state.total_frames += 1

            # schedule status
            self.state.armed = self.schedule.is_active_now()

            # detection throttling
            if frame_idx % max(1, self.config.DETECT_EVERY_N_FRAMES) == 0:
                detections = []
                if self.state.armed:
                    try:
                        detections = self.detector.detect(frame)
                    except Exception as e:
                        # Never let detection errors kill the capture loop
                        print(f"[secam] Detection error: {e}", flush=True)
                        detections = []
                    if detections:
                        self.state.detecting = True
                        self.state.last_detection_ts = time.time()
                        if self.config.SAVE_ON_DETECT:
                            self._maybe_save_frame(frame, detections)
                # cooldown / idle state
                if not detections:
                    if time.time() - self.state.last_detection_ts > self.config.ALERT_COOLDOWN_SEC:
                        self.state.detecting = False

            frame_idx += 1
            # Simple pacing
            time.sleep(interval)

    def _maybe_save_frame(self, frame: np.ndarray, detections) -> None:
        now = time.time()
        if now - self._last_saved_ts < self.config.SAVE_INTERVAL_SEC:
            return
        annotated = frame.copy()
        for det in detections:
            x, y, w, h = det.bbox
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 0, 255), 2)
        ts_str = time.strftime("%Y%m%d-%H%M%S")
        ms = int((now - int(now)) * 1000)
        filename = f"detect_{ts_str}_{ms:03d}.jpg"
        path = os.path.join(self.config.SAVE_DIR, filename)
        try:
            cv2.imwrite(path, annotated)
            self.state.saved_images_count += 1
            self._last_saved_ts = now
            self._enforce_retention()
        except Exception:
            pass

    def _enforce_retention(self) -> None:
        # Keep only newest MAX_SAVED_IMAGES
        try:
            files = [
                os.path.join(self.config.SAVE_DIR, f)
                for f in os.listdir(self.config.SAVE_DIR)
                if f.lower().endswith(".jpg")
            ]
        except FileNotFoundError:
            return
        if len(files) <= self.config.MAX_SAVED_IMAGES:
            return
        files.sort(key=lambda p: os.path.getmtime(p))  # oldest first
        to_delete = len(files) - self.config.MAX_SAVED_IMAGES
        for p in files[:to_delete]:
            try:
                os.remove(p)
            except Exception:
                pass
