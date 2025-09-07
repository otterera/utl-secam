"""Global configuration for the security camera application.

This module exposes configuration constants via the `Config` class. All values
are read from environment variables with sensible Raspberry Pi defaults.
"""

import os  # Standard library for environment and filesystem helpers
import re  # Robust parsing of numeric envs with comments/ranges


def _env_int(name: str, default: int) -> int:
    """Parse an integer from an environment variable robustly.

    Accepts values like "150", "150 # comment", or "120〜180" and returns the
    first integer found. Falls back to default if parsing fails.
    """
    val = os.getenv(name)
    if val is None:
        return default
    s = str(val).strip().strip('"').strip("'")
    m = re.search(r"-?\d+", s)
    if not m:
        return default
    try:
        return int(m.group(0))
    except Exception:
        return default


class Config:
    """Application configuration sourced from environment variables.

    This class provides class attributes so other modules can import settings as
    constants (e.g., `from security_cam.config import Config`). To override a
    setting, define the corresponding environment variable before launching the
    application.
    """
    # Camera
    FRAME_WIDTH = int(os.getenv("SC_FRAME_WIDTH", 320))  # Capture width in pixels
    FRAME_HEIGHT = int(os.getenv("SC_FRAME_HEIGHT", 240))  # Capture height in pixels
    CAPTURE_FPS = int(os.getenv("SC_CAPTURE_FPS", 1))  # Target FPS (kept low for Pi 3B CPU)
    CAMERA_BACKEND = os.getenv("SC_CAMERA_BACKEND", "auto").strip().lower()  # Camera backend: auto|picamera2|v4l2
    # Camera profile: standard color camera vs. NOIR (infrared, no IR-cut)
    CAMERA_PROFILE = os.getenv("SC_CAMERA_PROFILE", "standard").strip().lower()  # standard|noir

    # Detection
    DETECT_EVERY_N_FRAMES = int(os.getenv("SC_DETECT_EVERY_N_FRAMES", 5))  # Run detector every N frames
    DETECTOR_MIN_WIDTH = int(os.getenv("SC_DETECTOR_MIN_WIDTH", 48))  # Minimum person width
    DETECTOR_MIN_HEIGHT = int(os.getenv("SC_DETECTOR_MIN_HEIGHT", 96))  # Minimum person height
    DETECTOR_STRIDE = int(os.getenv("SC_DETECTOR_STRIDE", 8))  # HOG winStride step size
    DETECTOR_SCALE = float(os.getenv("SC_DETECTOR_SCALE", 1.05))  # HOG pyramid scale factor
    DETECTOR_HIT_THRESHOLD = float(os.getenv("SC_DETECTOR_HIT_THRESHOLD", 0))  # HOG SVM hit threshold
    # Detector backend: only motion is supported
    DETECTOR_BACKEND = "motion"

    # Motion detector (frame differencing) parameters
    MOTION_DOWNSCALE = float(os.getenv("SC_MOTION_DOWNSCALE", 1.0))  # 0.2..1.0, lower = faster/more smoothing
    MOTION_BLUR_KERNEL = int(os.getenv("SC_MOTION_BLUR_KERNEL", 3))  # odd int
    MOTION_DELTA_THRESH = int(os.getenv("SC_MOTION_DELTA_THRESH", 50))  # intensity threshold for diffs
    MOTION_DILATE_ITER = int(os.getenv("SC_MOTION_DILATE_ITER", 2))  # morphology to close gaps
    MOTION_MIN_PIXELS = _env_int("SC_MOTION_MIN_PIXELS", 250)  # changed pixels to trigger (post-resize)
    # When using motion backend, run camera auto-adjustments only on this cadence,
    # and pause motion detection briefly during the adjustment window to avoid
    # false triggers from brightness jumps.
    MOTION_ADJUST_PERIOD_SEC = float(os.getenv("SC_MOTION_ADJUST_PERIOD_SEC", 180.0))
    MOTION_ADJUST_PAUSE_SEC = float(os.getenv("SC_MOTION_ADJUST_PAUSE_SEC", 3.0))

    # Background subtraction settings removed (only motion is supported)

    # Saving
    # Normalize save directory: strip quotes/whitespace, expand ~ and $VARS, make absolute
    _SAVE_DIR_RAW = os.getenv("SC_SAVE_DIR", os.path.join("data", "captures"))
    _SAVE_DIR_NORM = str(_SAVE_DIR_RAW).strip().strip('"').strip("'")
    _SAVE_DIR_NORM = os.path.expanduser(os.path.expandvars(_SAVE_DIR_NORM))
    SAVE_DIR = os.path.abspath(_SAVE_DIR_NORM) if not os.path.isabs(_SAVE_DIR_NORM) else _SAVE_DIR_NORM  # absolute path
    SAVE_ON_DETECT = os.getenv("SC_SAVE_ON_DETECT", "1") == "1"  # Save when a detection occurs
    SAVE_INTERVAL_SEC = float(os.getenv("SC_SAVE_INTERVAL_SEC", 1.0))  # Minimum seconds between saves
    MAX_SAVED_IMAGES = int(os.getenv("SC_MAX_SAVED_IMAGES", 2000))  # Retention limit for saved images
    # Annotated and raw saving controls
    # Save an annotated copy (with boxes/labels) to SAVE_DIR
    SAVE_ANNOTATED_ON_DETECT = os.getenv("SC_SAVE_ANNOTATED_ON_DETECT", "1") == "1"
    # Legacy switch (kept for backward compatibility). Ignored in favor of
    # SAVE_ANNOTATED_ON_DETECT, but still parsed to avoid crashes in existing envs.
    ANNOTATE_SAVED = os.getenv("SC_ANNOTATE_SAVED", "1") == "1"
    # Optional additional raw (no-annotation) saves; default to SC_SAVE_DIR if RAW not provided
    _SAVE_DIR_RAW2 = os.getenv("SC_SAVE_DIR_RAW", os.getenv("SC_SAVE_DIR", os.path.join("data", "captures_raw")))
    _SAVE_DIR_RAW2_N = str(_SAVE_DIR_RAW2).strip().strip('"').strip("'")
    _SAVE_DIR_RAW2_N = os.path.expanduser(os.path.expandvars(_SAVE_DIR_RAW2_N))
    SAVE_DIR_RAW = os.path.abspath(_SAVE_DIR_RAW2_N) if not os.path.isabs(_SAVE_DIR_RAW2_N) else _SAVE_DIR_RAW2_N
    SAVE_RAW_ON_DETECT = os.getenv("SC_SAVE_RAW_ON_DETECT", "1") == "1"

    # Dashboard
    ALERT_COOLDOWN_SEC = float(os.getenv("SC_ALERT_COOLDOWN_SEC", 10.0))  # Keep alert banner visible this long
    GALLERY_LATEST_COUNT = int(os.getenv("SC_GALLERY_LATEST_COUNT", 12))  # Recent images shown on dashboard
    HOST = os.getenv("SC_HOST", "0.0.0.0")  # Flask bind host
    PORT = int(os.getenv("SC_PORT", 8000))  # Flask bind port
    DEBUG = os.getenv("SC_DEBUG", "0") == "1"  # Flask debug switch

    # Schedule (comma-separated daily windows, e.g., "22:00-06:00,12:30-13:30").
    # Empty means always armed.
    ACTIVE_WINDOWS = os.getenv("SC_ACTIVE_WINDOWS", "").strip()  # Daily arming windows

    # Frame orientation
    # Rotate frames by this many degrees (allowed: 0, 90, 180, 270). Default: 180 for upside-down installs.
    ROTATE_DEGREES = int(os.getenv("SC_ROTATE_DEGREES", 180))

    # NOIR (infrared) rendering and color correction
    # When using NOIR, colors are unreliable; choose rendering mode:
    #  - mono: render/detect in grayscale (recommended under IR illumination)
    #  - correct: attempt color correction via fixed colour gains
    NOIR_RENDER_MODE = os.getenv("SC_NOIR_RENDER_MODE", "mono").strip().lower()  # mono|correct
    # Fixed colour gains for Picamera2 when NOIR and correction is desired
    NOIR_COLOUR_GAIN_R = float(os.getenv("SC_NOIR_COLOUR_GAIN_R", 1.5))
    NOIR_COLOUR_GAIN_B = float(os.getenv("SC_NOIR_COLOUR_GAIN_B", 1.5))
    # Optional: use AWB even for NOIR in color mode (may still be unreliable under IR)
    NOIR_USE_AWB = os.getenv("SC_NOIR_USE_AWB", "0") == "1"
    # Optional: auto colour-balance for NOIR using gray-world (disables AWB)
    NOIR_AUTO_COLOUR = os.getenv("SC_NOIR_AUTO_COLOUR", "1") == "1"
    NOIR_COLOUR_ALPHA = float(os.getenv("SC_NOIR_COLOUR_ALPHA", 0.2))  # EMA smoothing
    NOIR_COLOUR_MIN = float(os.getenv("SC_NOIR_COLOUR_MIN", 0.5))
    NOIR_COLOUR_MAX = float(os.getenv("SC_NOIR_COLOUR_MAX", 3.0))
    NOIR_COLOUR_UPDATE_INTERVAL_SEC = float(os.getenv("SC_NOIR_COLOUR_UPDATE_INTERVAL_SEC", 2.0))

    # Automatic shutter (exposure time) adaptation (Picamera2 only)
    SHUTTER_ADAPT_ENABLE = os.getenv("SC_SHUTTER_ADAPT_ENABLE", "0") == "1"
    SHUTTER_MIN_US = int(os.getenv("SC_SHUTTER_MIN_US", 5000))  # 1/200s
    SHUTTER_MAX_US = int(os.getenv("SC_SHUTTER_MAX_US", 930_000))  # up to 0.93 second
    SHUTTER_STEP_US = int(os.getenv("SC_SHUTTER_STEP_US", 20_000))
    SHUTTER_RETURN_STEP_US = int(os.getenv("SC_SHUTTER_RETURN_STEP_US", 10_000))
    SHUTTER_BASE_US = int(os.getenv("SC_SHUTTER_BASE_US", 10_000))  # target when normal (~1/100s)
    SHUTTER_UPDATE_INTERVAL_SEC = float(os.getenv("SC_SHUTTER_UPDATE_INTERVAL_SEC", 1.0))

    # Adaptive sensitivity based on exposure (brightness) analysis
    ADAPTIVE_SENSITIVITY = os.getenv("SC_ADAPTIVE_SENSITIVITY", "1") == "1"  # Toggle adaptive behavior
    EXP_BRIGHT_MEAN = float(os.getenv("SC_EXP_BRIGHT_MEAN", 200))  # Over-exposure mean threshold
    EXP_DARK_MEAN = float(os.getenv("SC_EXP_DARK_MEAN", 40))  # Under-exposure mean threshold (enter)
    # Hysteresis: leave "under" only when mean exceeds EXIT threshold
    EXP_DARK_MEAN_EXIT = float(os.getenv("SC_EXP_DARK_MEAN_EXIT", 50))
    EXP_HIGH_CLIP_FRAC = float(os.getenv("SC_EXP_HIGH_CLIP_FRAC", 0.05))  # Fraction near max intensity
    EXP_LOW_CLIP_FRAC = float(os.getenv("SC_EXP_LOW_CLIP_FRAC", 0.05))   # Fraction near min intensity
    EXP_EMA_ALPHA = float(os.getenv("SC_EXP_EMA_ALPHA", 0.35))  # Smoothing factor for exposure metrics (0..1)
    ADAPT_HIT_THRESHOLD_DELTA = float(os.getenv("SC_ADAPT_HIT_THRESHOLD_DELTA", 0.5))  # Extra HOG threshold
    ADAPT_MIN_SIZE_SCALE = float(os.getenv("SC_ADAPT_MIN_SIZE_SCALE", 1.2))  # Increase min person size
    ADAPT_DETECT_STRIDE_SCALE = float(os.getenv("SC_ADAPT_DETECT_STRIDE_SCALE", 2.0))  # Slow detection cadence

    # Optional frame enhancement when exposure is poor (applied to displayed/detected frames)
    ENHANCE_ON_UNDER = os.getenv("SC_ENHANCE_ON_UNDER", "1") == "1"
    ENHANCE_UNDER_ALPHA = float(os.getenv("SC_ENHANCE_UNDER_ALPHA", 2.5))  # Contrast/gain multiplier
    ENHANCE_UNDER_BETA = float(os.getenv("SC_ENHANCE_UNDER_BETA", 20))  # Brightness offset (0..255)
    # Smoothing and hold to reduce flicker between bright/dark in dim scenes
    ENHANCE_BLEND_ALPHA = float(os.getenv("SC_ENHANCE_BLEND_ALPHA", 0.3))  # 0..1; higher = faster blending
    ENHANCE_HOLD_SEC = float(os.getenv("SC_ENHANCE_HOLD_SEC", 1.5))
    ENHANCE_ON_OVER = os.getenv("SC_ENHANCE_ON_OVER", "1") == "1"
    ENHANCE_OVER_ALPHA = float(os.getenv("SC_ENHANCE_OVER_ALPHA", 0.85))  # Reduce contrast
    ENHANCE_OVER_BETA = float(os.getenv("SC_ENHANCE_OVER_BETA", -10))  # Darken slightly

    # Automatic exposure EV-bias (camera-side, Picamera2 only)
    AE_EV_ADAPT_ENABLE = os.getenv("SC_AE_EV_ADAPT_ENABLE", "1") == "1"
    AE_EV_MIN = float(os.getenv("SC_AE_EV_MIN", -2.0))
    AE_EV_MAX = float(os.getenv("SC_AE_EV_MAX", 2.0))
    AE_EV_STEP = float(os.getenv("SC_AE_EV_STEP", 0.2))  # Per adjustment step
    AE_EV_RETURN_STEP = float(os.getenv("SC_AE_EV_RETURN_STEP", 0.1))  # Move back toward 0 when normal
    AE_EV_UPDATE_INTERVAL_SEC = float(os.getenv("SC_AE_EV_UPDATE_INTERVAL_SEC", 1.0))

    # Automatic analogue gain adjustment (Picamera2 only)
    GAIN_ADAPT_ENABLE = os.getenv("SC_GAIN_ADAPT_ENABLE", "1") == "1"
    GAIN_MIN = float(os.getenv("SC_GAIN_MIN", 1.0))
    GAIN_MAX = float(os.getenv("SC_GAIN_MAX", 12.0))
    GAIN_STEP = float(os.getenv("SC_GAIN_STEP", 0.5))
    GAIN_RETURN_STEP = float(os.getenv("SC_GAIN_RETURN_STEP", 0.25))
    GAIN_UPDATE_INTERVAL_SEC = float(os.getenv("SC_GAIN_UPDATE_INTERVAL_SEC", 1.0))

    # Face detection settings removed (only motion is supported)
