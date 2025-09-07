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
    CAPTURE_FPS = int(os.getenv("SC_CAPTURE_FPS", 5))  # Target FPS (kept low for Pi 3B CPU)
    CAMERA_BACKEND = os.getenv("SC_CAMERA_BACKEND", "auto").strip().lower()  # Camera backend: auto|picamera2|v4l2
    # Camera profile: standard color camera vs. NOIR (infrared, no IR-cut)
    CAMERA_PROFILE = os.getenv("SC_CAMERA_PROFILE", "noir").strip().lower()  # standard|noir

    # Detection
    DETECT_EVERY_N_FRAMES = int(os.getenv("SC_DETECT_EVERY_N_FRAMES", 1))  # Run detector every N frames

    # Motion detector (frame differencing) parameters
    MOTION_DOWNSCALE = float(os.getenv("SC_MOTION_DOWNSCALE", 1.0))  # 0.2..1.0, lower = faster/more smoothing
    """処理前に適用される縮小率。
    SC_MOTION_DOWNSCALE の値でフレームを縮小し、処理負荷を軽減しつつ小さな揺れを平滑化します。
    値が小さいほど高速で微細なちらつきに強くなりますが、細かい動きの検出力は低下します。
    例：640*480 → 0.5 → 320*240 に縮小して処理。
    """
    MOTION_BLUR_KERNEL = int(os.getenv("SC_MOTION_BLUR_KERNEL", 3))  # odd int
    """ガウシアンブラーの強さ。
    前のフレームとの絶対差分を計算します。
    値が大きいほどノイズ抑制効果が高くなりますが、小さく速い動きがぼやける可能性があります。
    5が標準、3は鋭敏、7以上は滑らか。"""

    MOTION_DELTA_THRESH = int(os.getenv("SC_MOTION_DELTA_THRESH", 50))  # intensity threshold for diffs
    """SC_MOTION_DELTA_THRESH（0〜255）
    差分の強度が SC_MOTION_DELTA_THRESH（0〜255）以上のピクセルを「変化あり」と判定します。
    ピクセルが「動いた」と判定されるための差分強度。
    値が小さいほど感度が高くなり、明るさの微小な変化も検出されます。
    10〜15：高感度、20〜30：厳しめ。"""

    MOTION_DILATE_ITER = int(os.getenv("SC_MOTION_DILATE_ITER", 2))  # morphology to close gaps
    """変化領域を何回膨張させるか。
    SC_MOTION_DILATE_ITER 回、変化領域を膨張させて隙間を埋めたり近接する動きを統合します。
    値が大きいほど穴埋めや近接領域の統合が進み、変化ピクセル数が増えます。
    1〜3が一般的、0は膨張なし（マスクが粗くなる）。"""

    _DEFALT_VALUE_MOTION_MIN_PIXELS = FRAME_WIDTH * FRAME_HEIGHT * 0.03
    MOTION_MIN_PIXELS = _env_int("SC_MOTION_MIN_PIXELS", _DEFALT_VALUE_MOTION_MIN_PIXELS)  # changed pixels to trigger (post-resize)
    # When using motion backend, run camera auto-adjustments only on this cadence,
    # and pause motion detection briefly during the adjustment window to avoid
    # false triggers from brightness jumps.
    """モーションと判定するために必要な変化ピクセル数（縮小後の画像で）。
    ピクセル数のカウント + 輪郭検出
    変化したピクセル数が SC_MOTION_MIN_PIXELS 以上なら、モーションと判定し、動いている領域のバウンディングボックスを返します。
    「どれくらいの領域が変化すればモーションとみなすか」の基準。"""

    MOTION_ADJUST_PERIOD_SEC = float(os.getenv("SC_MOTION_ADJUST_PERIOD_SEC", 180.0))
    """ Auto-adjustment cadence when using motion detection backend
    例えば180.0に設定した場合、180秒ごとにカメラの自動調整を実行します
    自動調整は例えば、露出やホワイトバランスの再調整を含みます"""

    MOTION_ADJUST_PAUSE_SEC = float(os.getenv("SC_MOTION_ADJUST_PAUSE_SEC", 0.5))
    """ Pause motion detection this long after an adjustment
    例えば3.0に設定した場合、自動調整後3秒間はモーション検出を一時停止します
    これにより、自動調整を原因とする露出の急激な変化による誤検出を防ぎます"""

    # Saving
    # Normalize save directory: strip quotes/whitespace, expand ~ and $VARS, make absolute
    _SAVE_DIR_RAW = os.getenv("SC_SAVE_DIR", os.path.join("data", "captures"))
    _SAVE_DIR_NORM = str(_SAVE_DIR_RAW).strip().strip('"').strip("'")
    _SAVE_DIR_NORM = os.path.expanduser(os.path.expandvars(_SAVE_DIR_NORM))
    SAVE_DIR = os.path.abspath(_SAVE_DIR_NORM) if not os.path.isabs(_SAVE_DIR_NORM) else _SAVE_DIR_NORM  # absolute path
    SAVE_ON_DETECT = os.getenv("SC_SAVE_ON_DETECT", "1") == "1"  # Save when a detection occurs
    SAVE_INTERVAL_SEC = float(os.getenv("SC_SAVE_INTERVAL_SEC", 1.0))  # Minimum seconds between saves
    MAX_SAVED_IMAGES = int(os.getenv("SC_MAX_SAVED_IMAGES", 100))  # Retention limit for saved images

    # Annotated and raw saving controls
    # Save an annotated copy (with boxes/labels) to SAVE_DIR
    SAVE_ANNOTATED_ON_DETECT = os.getenv("SC_SAVE_ANNOTATED_ON_DETECT", "1") == "1"
    # Legacy switch (kept for backward compatibility). Ignored in favor of
    # SAVE_ANNOTATED_ON_DETECT, but still parsed to avoid crashes in existing envs.
    ANNOTATE_SAVED = os.getenv("SC_ANNOTATE_SAVED", "1") == "1"
    # Optional additional raw (no-annotation) saves; default to SC_SAVE_DIR if RAW not provided
    _SAVE_DIR_RAW2 = os.getenv("SC_SAVE_DIR_RAW", os.path.join("data", "captures_raw"))
    _SAVE_DIR_RAW2_N = str(_SAVE_DIR_RAW2).strip().strip('"').strip("'")
    _SAVE_DIR_RAW2_N = os.path.expanduser(os.path.expandvars(_SAVE_DIR_RAW2_N))
    SAVE_DIR_RAW = os.path.abspath(_SAVE_DIR_RAW2_N) if not os.path.isabs(_SAVE_DIR_RAW2_N) else _SAVE_DIR_RAW2_N
    SAVE_RAW_ON_DETECT = os.getenv("SC_SAVE_RAW_ON_DETECT", "1") == "1"

    # Dashboard
    ALERT_COOLDOWN_SEC = float(os.getenv("SC_ALERT_COOLDOWN_SEC", 10.0))  # Keep alert banner visible this long
    GALLERY_LATEST_COUNT = int(os.getenv("SC_GALLERY_LATEST_COUNT", 18))  # Recent images shown on dashboard
    HOST = os.getenv("SC_HOST", "0.0.0.0")  # Flask bind host
    PORT = int(os.getenv("SC_PORT", 8000))  # Flask bind port
    DEBUG = os.getenv("SC_DEBUG", "0") == "1"  # Flask debug switch

    # Schedule (comma-separated daily windows, e.g., "22:00-06:00,12:30-13:30").
    # Empty means always armed.
    ACTIVE_WINDOWS = os.getenv("SC_ACTIVE_WINDOWS", "").strip()  # Daily arming windows

    # Frame orientation
    # Rotate frames by this many degrees (allowed: 0, 90, 180, 270). Default: 180 for upside-down installs.
    ROTATE_DEGREES = int(os.getenv("SC_ROTATE_DEGREES", 180))

    # NOIR (infrared) handling: always render grayscale under IR

    # Automatic shutter (exposure time) adaptation (Picamera2 only)
    SHUTTER_ADAPT_ENABLE = os.getenv("SC_SHUTTER_ADAPT_ENABLE", "0") == "1"
    SHUTTER_MIN_US = int(os.getenv("SC_SHUTTER_MIN_US", 5000))  # 1/200s (5 ms)  minimum
    SHUTTER_MAX_US = int(os.getenv("SC_SHUTTER_MAX_US", 50_000))  # up to 1/20s (50 ms)  maximum
    SHUTTER_STEP_US = int(os.getenv("SC_SHUTTER_STEP_US", 10_000))  # per adjustment step (10 ms)
    SHUTTER_RETURN_STEP_US = int(os.getenv("SC_SHUTTER_RETURN_STEP_US", 5_000))  # move back toward base when normal (5 ms)
    SHUTTER_BASE_US = int(os.getenv("SC_SHUTTER_BASE_US", 10_000))  # target when normal (~1/100s) (10 ms)
    SHUTTER_UPDATE_INTERVAL_SEC = float(os.getenv("SC_SHUTTER_UPDATE_INTERVAL_SEC", 1.0))  # adjustment cadence

    # Adaptive sensitivity based on exposure (brightness) analysis
    ADAPTIVE_SENSITIVITY = os.getenv("SC_ADAPTIVE_SENSITIVITY", "1") == "1"  # Toggle adaptive behavior
    EXP_BRIGHT_MEAN = float(os.getenv("SC_EXP_BRIGHT_MEAN", 200))  # Over-exposure mean threshold
    EXP_DARK_MEAN = float(os.getenv("SC_EXP_DARK_MEAN", 50))  # Under-exposure mean threshold (enter)
    # Hysteresis: leave "under" only when mean exceeds EXIT threshold
    EXP_DARK_MEAN_EXIT = float(os.getenv("SC_EXP_DARK_MEAN_EXIT", 60))
    EXP_HIGH_CLIP_FRAC = float(os.getenv("SC_EXP_HIGH_CLIP_FRAC", 0.05))  # Fraction near max intensity
    EXP_LOW_CLIP_FRAC = float(os.getenv("SC_EXP_LOW_CLIP_FRAC", 0.03))   # Fraction near min intensity
    EXP_EMA_ALPHA = float(os.getenv("SC_EXP_EMA_ALPHA", 0.35))  # Smoothing factor for exposure metrics (0..1)
    ADAPT_HIT_THRESHOLD_DELTA = float(os.getenv("SC_ADAPT_HIT_THRESHOLD_DELTA", 0.5))  # Extra HOG threshold
    ADAPT_MIN_SIZE_SCALE = float(os.getenv("SC_ADAPT_MIN_SIZE_SCALE", 1.2))  # Increase min person size
    ADAPT_DETECT_STRIDE_SCALE = float(os.getenv("SC_ADAPT_DETECT_STRIDE_SCALE", 2.0))  # Slow detection cadence

    # Optional frame enhancement when exposure is poor (applied to displayed/detected frames)
    ENHANCE_ON_UNDER = os.getenv("SC_ENHANCE_ON_UNDER", "1") == "1"
    ENHANCE_UNDER_ALPHA = float(os.getenv("SC_ENHANCE_UNDER_ALPHA", 2.5))  # Contrast/gain multiplier
    ENHANCE_UNDER_BETA = float(os.getenv("SC_ENHANCE_UNDER_BETA", 20))  # Brightness offset (0..255)
    # Smoothing and hold to reduce flicker between bright/dark in dim scenes
    ENHANCE_BLEND_ALPHA = float(os.getenv("SC_ENHANCE_BLEND_ALPHA", 0.4))  # 0..1; higher = faster blending
    ENHANCE_HOLD_SEC = float(os.getenv("SC_ENHANCE_HOLD_SEC", 2.0))
    ENHANCE_ON_OVER = os.getenv("SC_ENHANCE_ON_OVER", "1") == "1"
    ENHANCE_OVER_ALPHA = float(os.getenv("SC_ENHANCE_OVER_ALPHA", 0.85))  # Reduce contrast
    ENHANCE_OVER_BETA = float(os.getenv("SC_ENHANCE_OVER_BETA", -10))  # Darken slightly

    # Automatic exposure EV-bias (camera-side, Picamera2 only)
    AE_EV_ADAPT_ENABLE = os.getenv("SC_AE_EV_ADAPT_ENABLE", "1") == "1"
    AE_EV_MIN = float(os.getenv("SC_AE_EV_MIN", -2.0))
    AE_EV_MAX = float(os.getenv("SC_AE_EV_MAX", 2.0))
    AE_EV_STEP = float(os.getenv("SC_AE_EV_STEP", 0.2))  # Per adjustment step
    AE_EV_RETURN_STEP = float(os.getenv("SC_AE_EV_RETURN_STEP", 0.1))  # Move back toward 0 when normal
    AE_EV_UPDATE_INTERVAL_SEC = float(os.getenv("SC_AE_EV_UPDATE_INTERVAL_SEC", 0.5))

    # Automatic analogue gain adjustment (Picamera2 only)
    GAIN_ADAPT_ENABLE = os.getenv("SC_GAIN_ADAPT_ENABLE", "1") == "1"
    GAIN_MIN = float(os.getenv("SC_GAIN_MIN", 1.0))
    GAIN_MAX = float(os.getenv("SC_GAIN_MAX", 12.0))
    GAIN_STEP = float(os.getenv("SC_GAIN_STEP", 0.5))
    GAIN_RETURN_STEP = float(os.getenv("SC_GAIN_RETURN_STEP", 0.25))
    GAIN_UPDATE_INTERVAL_SEC = float(os.getenv("SC_GAIN_UPDATE_INTERVAL_SEC", 0.5))
