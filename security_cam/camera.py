"""Camera backends and factory for the security camera app.

Provides a minimal interface to either Picamera2 (CSI cameras) or OpenCV’s
VideoCapture (V4L2 devices like USB webcams). Frames are returned as BGR
NumPy arrays compatible with OpenCV.
"""

import time  # Sleep on read failures to reduce busy looping
from typing import Optional, Tuple  # Type hints for clarity

import numpy as np  # Frame arrays

from .config import Config  # Global configuration


class BaseCamera:
    """Abstract camera interface returning BGR frames.

    Subclasses must implement `start()`, `read()`, and `stop()`.
    """

    def start(self) -> None:
        """Initialize and start the camera stream."""
        raise NotImplementedError

    def read(self) -> Optional[np.ndarray]:
        """Read a single BGR frame.

        Returns:
          A NumPy array in BGR order, or None if a frame is not available.
        """
        raise NotImplementedError

    def stop(self) -> None:
        """Stop and release camera resources."""
        pass

    # Optional camera-side controls (Picamera2 backend implements these)
    def supports_ev(self) -> bool:
        """Return True if this camera supports EV-bias control."""
        return False

    def set_ev(self, ev: float) -> bool:
        """Set exposure value (EV-bias) if supported.

        Args:
          ev: Exposure bias (positive to brighten, negative to darken).

        Returns:
          True if applied; False if unsupported or failed.
        """
        return False

    def set_auto_exposure(self, enable: bool) -> bool:
        """Enable or disable camera auto exposure if supported.

        Returns:
          True if applied; False otherwise.
        """
        return False

    def supports_gain(self) -> bool:
        """Return True if this camera supports analogue gain control."""
        return False

    def set_gain(self, gain: float) -> bool:
        """Set analogue gain if supported.

        Args:
          gain: Requested analogue gain (e.g., 1.0–8.0).

        Returns:
          True if applied; False if unsupported or failed.
        """
        return False


class PiCamera2Wrapper(BaseCamera):
    """PiCamera2-based camera backend for CSI-connected camera modules."""

    def __init__(self, size: Tuple[int, int]) -> None:
        """Create a camera with a given frame size.

        Args:
          size: `(width, height)` capture resolution.
        """
        self.size = size  # Desired capture size
        self.picam2 = None  # Will hold Picamera2 instance
        self._started = False  # Tracks start state

    def start(self) -> None:
        """Configure and start Picamera2 streaming."""
        from picamera2 import Picamera2  # Imported lazily to avoid hard dependency

        self.picam2 = Picamera2()  # Create camera instance
        w, h = self.size  # Unpack desired width and height
        config = self.picam2.create_video_configuration(
            main={"size": (w, h), "format": "RGB888"}  # Request RGB frames
        )
        self.picam2.configure(config)  # Apply configuration
        # Ensure AE is enabled; EV-bias relies on auto-exposure being active
        try:
            self.picam2.set_controls({"AeEnable": True})
        except Exception:
            pass
        # Handle NOIR (infrared) profile: adjust AWB/colour gains
        try:
            if Config.CAMERA_PROFILE == "noir":
                if Config.NOIR_RENDER_MODE == "correct":
                    if Config.NOIR_USE_AWB:
                        # Let AWB attempt correction (works better under visible light)
                        self.picam2.set_controls({"AwbEnable": True})
                    elif Config.NOIR_AUTO_COLOUR:
                        # We'll drive ColourGains dynamically in the service
                        self.picam2.set_controls({"AwbEnable": False})
                    else:
                        # Apply fixed gains to reduce cast
                        self.picam2.set_controls({
                            "AwbEnable": False,
                            "ColourGains": (float(Config.NOIR_COLOUR_GAIN_R), float(Config.NOIR_COLOUR_GAIN_B)),
                        })
                else:
                    # Prefer grayscale rendering; keep AWB off to avoid odd shifts
                    self.picam2.set_controls({"AwbEnable": False})
            else:
                # Standard profile: allow AWB
                self.picam2.set_controls({"AwbEnable": True})
        except Exception:
            # If any control is unsupported, ignore quietly
            pass
        self.picam2.start()  # Start the camera
        self._started = True  # Mark as started

    def read(self) -> Optional[np.ndarray]:
        """Capture a frame and return it in BGR order."""
        if not self._started:  # Guard if not started yet
            return None
        # Picamera2 returns RGB; convert to OpenCV’s expected BGR order
        arr = self.picam2.capture_array()  # Get the latest frame as an array
        if arr is None:  # If no frame is available yet
            return None
        return arr[:, :, ::-1].copy()  # Reverse channels RGB->BGR

    def stop(self) -> None:
        """Stop streaming and release resources."""
        try:
            if self.picam2:  # If a camera instance exists
                self.picam2.stop()  # Stop streaming
        except Exception:
            # Ignore errors during shutdown to keep cleanup robust
            pass
        self._started = False  # Mark as stopped

    def supports_ev(self) -> bool:
        """Picamera2 supports EV-bias when AE is enabled."""
        return True

    def set_ev(self, ev: float) -> bool:
        """Apply an EV-bias to the auto-exposure algorithm.

        Args:
          ev: Exposure bias value to set.

        Returns:
          True if controls were applied successfully; False otherwise.
        """
        try:
            if not self._started or self.picam2 is None:
                return False
            # Keep AE enabled and set the exposure value (bias)
            self.picam2.set_controls({"AeEnable": True, "ExposureValue": float(ev)})
            return True
        except Exception:
            return False

    def set_auto_exposure(self, enable: bool) -> bool:
        """Toggle Picamera2 AE (auto exposure)."""
        try:
            if not self._started or self.picam2 is None:
                return False
            self.picam2.set_controls({"AeEnable": bool(enable)})
            return True
        except Exception:
            return False

    def supports_gain(self) -> bool:
        """Picamera2 exposes AnalogueGain control."""
        return True

    def set_gain(self, gain: float) -> bool:
        """Attempt to set analogue gain on the camera.

        Note: When AE is enabled, the driver may override this value. It still
        often works as a hint. For full manual control, AE would be disabled,
        which we avoid here to keep auto-exposure active.
        """
        try:
            if not self._started or self.picam2 is None:
                return False
            self.picam2.set_controls({"AnalogueGain": float(gain)})
            return True
        except Exception:
            return False

    def supports_shutter(self) -> bool:
        """Picamera2 supports manual ExposureTime control."""
        return True

    def set_shutter(self, exposure_time_us: int) -> bool:
        """Set manual exposure time (microseconds) and adjust frame duration.

        This disables AE to allow manual exposure control.
        """
        try:
            if not self._started or self.picam2 is None:
                return False
            us = int(exposure_time_us)
            # Ensure frame duration can accommodate the exposure time
            limits = (us, max(us, us + 1000))
            self.picam2.set_controls({
                "AeEnable": False,
                "ExposureTime": us,
                "FrameDurationLimits": limits,
            })
            return True
        except Exception:
            return False


class Cv2V4L2Camera(BaseCamera):
    """OpenCV VideoCapture backend for V4L2 devices (e.g., USB webcams)."""

    def __init__(self, index: int, size: Tuple[int, int], fps: int) -> None:
        """Create a V4L2 camera.

        Args:
          index: V4L2 device index (e.g., 0 for /dev/video0).
          size: `(width, height)` capture resolution.
          fps: Requested frames per second.
        """
        import cv2  # Imported here to avoid global import cost if unused

        self.cv2 = cv2  # Save module reference for property constants
        self.index = index  # Device index
        self.size = size  # Desired capture size
        self.fps = fps  # Target FPS
        self.cap = None  # Will hold cv2.VideoCapture instance

    def start(self) -> None:
        """Open the V4L2 device and set basic properties."""
        self.cap = self.cv2.VideoCapture(self.index)  # Open device
        w, h = self.size  # Unpack target size
        self.cap.set(self.cv2.CAP_PROP_FRAME_WIDTH, w)  # Set width
        self.cap.set(self.cv2.CAP_PROP_FRAME_HEIGHT, h)  # Set height
        self.cap.set(self.cv2.CAP_PROP_FPS, self.fps)  # Set FPS

    def read(self) -> Optional[np.ndarray]:
        """Grab a frame from the V4L2 device."""
        if self.cap is None:  # Not started
            return None
        ok, frame = self.cap.read()  # Try to read a frame
        if not ok:  # If read failed, back off briefly
            time.sleep(0.01)
            return None
        return frame  # Frame is already BGR

    def stop(self) -> None:
        """Release the V4L2 device."""
        try:
            if self.cap is not None:  # If opened
                self.cap.release()  # Release device
        except Exception:
            # Suppress release errors during shutdown
            pass


def make_camera() -> BaseCamera:
    """Factory to create the appropriate camera backend based on config.

    Returns:
      An instance of `BaseCamera` using either Picamera2 or V4L2.
    """
    size = (Config.FRAME_WIDTH, Config.FRAME_HEIGHT)  # Desired capture size
    backend = Config.CAMERA_BACKEND  # Requested backend
    if backend == "picamera2":  # Force Picamera2
        return PiCamera2Wrapper(size=size)
    if backend == "v4l2":  # Force V4L2
        return Cv2V4L2Camera(index=0, size=size, fps=Config.CAPTURE_FPS)

    # Auto: try Picamera2 first, fall back to V4L2
    try:
        import importlib  # Dynamic import to test availability

        importlib.import_module("picamera2")  # Raises if unavailable
        return PiCamera2Wrapper(size=size)
    except Exception:
        return Cv2V4L2Camera(index=0, size=size, fps=Config.CAPTURE_FPS)
