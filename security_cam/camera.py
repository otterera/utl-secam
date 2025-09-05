import time
from typing import Optional, Tuple

import numpy as np

from .config import Config


class BaseCamera:
    def start(self) -> None:
        raise NotImplementedError

    def read(self) -> Optional[np.ndarray]:
        """Return a BGR frame or None if unavailable."""
        raise NotImplementedError

    def stop(self) -> None:
        pass


class PiCamera2Wrapper(BaseCamera):
    def __init__(self, size: Tuple[int, int]) -> None:
        self.size = size
        self.picam2 = None
        self._started = False

    def start(self) -> None:
        from picamera2 import Picamera2

        self.picam2 = Picamera2()
        w, h = self.size
        config = self.picam2.create_video_configuration(
            main={"size": (w, h), "format": "RGB888"}
        )
        self.picam2.configure(config)
        self.picam2.start()
        self._started = True

    def read(self) -> Optional[np.ndarray]:
        if not self._started:
            return None
        # picamera2 returns RGB; convert to BGR for OpenCV
        arr = self.picam2.capture_array()
        if arr is None:
            return None
        return arr[:, :, ::-1].copy()

    def stop(self) -> None:
        try:
            if self.picam2:
                self.picam2.stop()
        except Exception:
            pass
        self._started = False


class Cv2V4L2Camera(BaseCamera):
    def __init__(self, index: int, size: Tuple[int, int], fps: int) -> None:
        import cv2

        self.cv2 = cv2
        self.index = index
        self.size = size
        self.fps = fps
        self.cap = None

    def start(self) -> None:
        self.cap = self.cv2.VideoCapture(self.index)
        w, h = self.size
        self.cap.set(self.cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(self.cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.cap.set(self.cv2.CAP_PROP_FPS, self.fps)

    def read(self) -> Optional[np.ndarray]:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok:
            time.sleep(0.01)
            return None
        return frame

    def stop(self) -> None:
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass


def make_camera() -> BaseCamera:
    size = (Config.FRAME_WIDTH, Config.FRAME_HEIGHT)
    # Try PiCamera2 first
    try:
        import importlib

        importlib.import_module("picamera2")
        return PiCamera2Wrapper(size=size)
    except Exception:
        # Fallback to OpenCV V4L2
        return Cv2V4L2Camera(index=0, size=size, fps=Config.CAPTURE_FPS)

