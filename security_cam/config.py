import os


class Config:
    # Camera
    FRAME_WIDTH = int(os.getenv("SC_FRAME_WIDTH", 320))
    FRAME_HEIGHT = int(os.getenv("SC_FRAME_HEIGHT", 240))
    CAPTURE_FPS = int(os.getenv("SC_CAPTURE_FPS", 1))  # lower for Pi 3B CPU

    # Detection
    DETECT_EVERY_N_FRAMES = int(os.getenv("SC_DETECT_EVERY_N_FRAMES", 3))
    DETECTOR_MIN_WIDTH = int(os.getenv("SC_DETECTOR_MIN_WIDTH", 48))
    DETECTOR_MIN_HEIGHT = int(os.getenv("SC_DETECTOR_MIN_HEIGHT", 96))
    DETECTOR_STRIDE = int(os.getenv("SC_DETECTOR_STRIDE", 8))
    DETECTOR_SCALE = float(os.getenv("SC_DETECTOR_SCALE", 1.05))
    DETECTOR_HIT_THRESHOLD = float(os.getenv("SC_DETECTOR_HIT_THRESHOLD", 0))

    # Saving
    SAVE_DIR = os.getenv("SC_SAVE_DIR", os.path.join("data", "captures"))
    SAVE_ON_DETECT = os.getenv("SC_SAVE_ON_DETECT", "1") == "1"
    SAVE_INTERVAL_SEC = float(os.getenv("SC_SAVE_INTERVAL_SEC", 1.0))
    MAX_SAVED_IMAGES = int(os.getenv("SC_MAX_SAVED_IMAGES", 2000))

    # Dashboard
    ALERT_COOLDOWN_SEC = float(os.getenv("SC_ALERT_COOLDOWN_SEC", 10.0))
    GALLERY_LATEST_COUNT = int(os.getenv("SC_GALLERY_LATEST_COUNT", 12))
    HOST = os.getenv("SC_HOST", "0.0.0.0")
    PORT = int(os.getenv("SC_PORT", 8000))
    DEBUG = os.getenv("SC_DEBUG", "0") == "1"

