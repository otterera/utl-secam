"""Background capture/detection service for the security camera app."""

import os
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np

from .camera import BaseCamera, make_camera
from .config import Config
from .detector import MotionDetector
from .schedule import DailySchedule


@dataclass
class ServiceState:
    """Observable service state used by the web API and dashboard."""
    detecting: bool = False
    last_detection_ts: float = 0.0
    saved_images_count: int = 0
    total_frames: int = 0
    armed: bool = True
    exposure_state: str = "unknown"  # normal|over|under
    exposure_mean: float = 0.0
    exposure_low_clip: float = 0.0
    exposure_high_clip: float = 0.0
    detect_stride: int = 1
    hit_threshold: float = 0.0
    person_count: int = 0
    face_count: int = 0
    last_kinds: List[str] = field(default_factory=list)
    ev_bias: float = 0.0
    gain: float = 0.0
    shutter_us: int = 0


class SecurityCamService:
    """Owns the camera loop, detection cadence, and image saving."""

    def __init__(self) -> None:
        """Initialize components, state, and adaptive tuning caches."""
        self.config = Config
        self.camera: BaseCamera = make_camera()
        self.detector = MotionDetector()
        self._detector_backend = "motion"
        self.state = ServiceState()
        self.schedule = DailySchedule(self.config.ACTIVE_WINDOWS)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._last_saved_ts: float = 0.0
        os.makedirs(self.config.SAVE_DIR, exist_ok=True)
        # Ensure raw save directory exists too (for /captures_raw and raw saving)
        try:
            os.makedirs(self.config.SAVE_DIR_RAW, exist_ok=True)
        except Exception:
            pass
        # Adaptive internals
        self._detect_stride_base = max(1, self.config.DETECT_EVERY_N_FRAMES)
        self._detect_stride_dyn = self._detect_stride_base
        # Legacy HOG-related dynamic parameters removed
        self._exp_mean_ema = 0.0
        self._exp_low_clip_ema = 0.0
        self._exp_high_clip_ema = 0.0
        # Enhancement parameters (contrast/brightness) applied when exposure is poor
        self._enh_alpha: float = 1.0
        self._enh_beta: float = 0.0
        self._enh_tgt_alpha: float = 1.0
        self._enh_tgt_beta: float = 0.0
        self._enh_hold_until: float = 0.0
        # Camera EV-bias adaptation (Picamera2): current bias and last update time
        self._ev_bias: float = 0.0
        self._ev_last_update: float = 0.0
        # Camera analogue gain adaptation
        self._gain_value: float = float(getattr(self.config, "GAIN_MIN", 1.0))
        self._gain_last_update: float = 0.0
        # Camera shutter (exposure time) adaptation
        self._shutter_us: int = int(getattr(self.config, "SHUTTER_BASE_US", 10_000))
        self._shutter_last_update: float = 0.0
        self._manual_exposure: bool = False
        # NOIR color correction removed; always convert to mono in service when profile=noir
        # Face detection debounce (removed with non-motion detectors)
        # Motion-backend adjustment cadence and pause window
        self._adjust_last_ts: float = 0.0
        self._adjust_pause_until: float = 0.0
        self._seed_at_resume: bool = False
        self._last_frame_ts: float = 0.0
        # Initialize public state mirrors
        self.state.ev_bias = float(self._ev_bias)
        self.state.gain = float(self._gain_value)
        self.state.shutter_us = int(self._shutter_us)

    # Public API
    def start(self) -> None:
        """Start background thread (camera starts inside thread)."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request shutdown and release camera resources."""
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.camera.stop()

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Return a copy of the most recent frame, or None."""
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def get_status(self) -> ServiceState:
        """Return the current service state snapshot."""
        return self.state

    def list_latest_images(self, limit: int) -> List[str]:
        """List newest saved images up to `limit` (absolute paths)."""
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
        """Worker loop: read frames, adapt, detect, save, repeat."""
        frame_idx = 0
        frame_interval = 1.0 / max(1, self.config.CAPTURE_FPS)
        next_frame_ts = time.time()
        # Initialize camera here so Flask can start even if camera blocks
        started = False
        while not self._stop.is_set():
            # Pace the loop to respect CAPTURE_FPS precisely, regardless of processing time
            now_loop = time.time()
            if now_loop < next_frame_ts:
                time.sleep(min(0.1, next_frame_ts - now_loop))
                continue
            # Schedule next frame time; if we fell behind, reset to avoid bursts
            next_frame_ts += frame_interval
            if next_frame_ts < now_loop:
                next_frame_ts = now_loop + frame_interval
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
            # Seed after idle/no-frame gaps to avoid stale baseline
            now_frame = time.time()
            if self._last_frame_ts and (now_frame - self._last_frame_ts) > float(self.config.SEED_AFTER_IDLE_SEC):
                try:
                    self.detector.reset()
                except Exception:
                    pass
                self._seed_at_resume = True
            self._last_frame_ts = now_frame

            # Apply fixed rotation (e.g., for upside-down installation)
            rot = int(self.config.ROTATE_DEGREES)
            if rot == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif rot == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif rot == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # If using NOIR profile, render mono for stable detection/appearance under IR.
            if self.config.CAMERA_PROFILE == "noir":
                try:
                    # Prefer camera luma (Y) when available to avoid extra conversion
                    y = None
                    try:
                        if hasattr(self.camera, "get_last_luma"):
                            y = self.camera.get_last_luma()
                    except Exception:
                        y = None
                    if y is not None:
                        gray = y
                        # Apply the same rotation to luma as we applied to the frame
                        if rot == 180:
                            gray = cv2.rotate(gray, cv2.ROTATE_180)
                        elif rot == 90:
                            gray = cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)
                        elif rot == 270:
                            gray = cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    else:
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                except Exception:
                    pass

            # exposure analysis and adaptive sensitivity (also selects enhancement)
            self._update_exposure_and_adapt(frame)

            # Optionally enhance frame when under/over exposed
            proc = frame
            if abs(self._enh_alpha - 1.0) > 1e-3 or abs(self._enh_beta) > 1e-3:
                try:
                    proc = cv2.convertScaleAbs(frame, alpha=self._enh_alpha, beta=self._enh_beta)
                except Exception:
                    proc = frame

            # store latest (processed) frame
            with self._frame_lock:
                self._latest_frame = proc
            self.state.total_frames += 1

            # schedule status
            self.state.armed = self.schedule.is_active_now()

            self.state.detect_stride = int(self._detect_stride_dyn)
            self.state.hit_threshold = 0.0

            # detection throttling (cadence may be adapted by exposure)
            if frame_idx % max(1, int(self._detect_stride_dyn)) == 0:
                detections = []
                # Pause motion detection during scheduled camera adjustments
                paused_for_adjust = (
                    self._detector_backend == "motion" and time.time() < self._adjust_pause_until
                )
                # If pause window ended and we owe a seed, seed now and skip this detection tick
                seeded_now = False
                if self._seed_at_resume and not paused_for_adjust:
                    try:
                        self.detector.seed(proc)
                    except Exception:
                        pass
                    self._seed_at_resume = False
                    seeded_now = True

                if self.state.armed and not paused_for_adjust and not seeded_now:
                    try:
                        detections = self.detector.detect(proc)
                    except Exception as e:
                        # Never let detection errors kill the capture loop
                        print(f"[secam] Detection error: {e}", flush=True)
                        detections = []
                    if detections:
                        self.state.detecting = True
                        self.state.last_detection_ts = time.time()
                        # Update counts and kinds for UI/API
                        persons = sum(1 for d in detections if getattr(d, "kind", "person") == "person")
                        faces = sum(1 for d in detections if getattr(d, "kind", "") == "face")
                        kinds = []
                        if persons:
                            kinds.append("person")
                        if faces:
                            kinds.append("face")
                        self.state.person_count = persons
                        self.state.face_count = faces
                        self.state.last_kinds = kinds
                        if self.config.SAVE_ON_DETECT:
                            self._maybe_save_frame(proc, detections)
                # cooldown / idle state
                if not detections:
                    if time.time() - self.state.last_detection_ts > self.config.ALERT_COOLDOWN_SEC:
                        self.state.detecting = False
                        self.state.person_count = 0
                        self.state.face_count = 0
                        self.state.last_kinds = []
                        pass

            frame_idx += 1

    def _update_exposure_and_adapt(self, frame: np.ndarray) -> None:
        """Update exposure metrics and adjust sensitivity/cadence accordingly."""
        if not self.config.ADAPTIVE_SENSITIVITY:
            self.state.exposure_state = "off"
            self._detect_stride_dyn = self._detect_stride_base
            return
        # Compute metrics
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean = float(gray.mean())
        # Use tight thresholds for clip percentages
        low_clip = float((gray <= 5).mean())
        high_clip = float((gray >= 250).mean())
        # EMA to stabilize (configurable smoothing factor)
        alpha = float(self.config.EXP_EMA_ALPHA)
        self._exp_mean_ema = (1 - alpha) * self._exp_mean_ema + alpha * mean
        self._exp_low_clip_ema = (1 - alpha) * self._exp_low_clip_ema + alpha * low_clip
        self._exp_high_clip_ema = (1 - alpha) * self._exp_high_clip_ema + alpha * high_clip

        # Apply hysteresis for "under" state using EXIT threshold to leave under-exposed condition
        prev_state = self.state.exposure_state
        if prev_state == "under":
            under = (self._exp_low_clip_ema > self.config.EXP_LOW_CLIP_FRAC) or (self._exp_mean_ema < self.config.EXP_DARK_MEAN_EXIT)
        else:
            under = (self._exp_low_clip_ema > self.config.EXP_LOW_CLIP_FRAC) or (self._exp_mean_ema < self.config.EXP_DARK_MEAN)
        over = (self._exp_high_clip_ema > self.config.EXP_HIGH_CLIP_FRAC) or (self._exp_mean_ema > self.config.EXP_BRIGHT_MEAN)
        if over:
            exp_state = "over"
        elif under:
            exp_state = "under"
        else:
            exp_state = "normal"

        self.state.exposure_state = exp_state
        self.state.exposure_mean = self._exp_mean_ema
        self.state.exposure_low_clip = self._exp_low_clip_ema
        self.state.exposure_high_clip = self._exp_high_clip_ema

        # Adapt parameters
        if exp_state in ("over", "under"):
            # No-op for motion backend
            self._detect_stride_dyn = int(max(1, self._detect_stride_base * self.config.ADAPT_DETECT_STRIDE_SCALE))
        else:
            # No-op for motion backend
            self._detect_stride_dyn = self._detect_stride_base

        # Choose enhancement target with hold + blend to avoid flicker
        target_alpha, target_beta = 1.0, 0.0
        now = time.time()
        if exp_state == "under" and self.config.ENHANCE_ON_UNDER:
            target_alpha = float(self.config.ENHANCE_UNDER_ALPHA)
            target_beta = float(self.config.ENHANCE_UNDER_BETA)
            self._enh_hold_until = max(self._enh_hold_until, now + float(self.config.ENHANCE_HOLD_SEC))
        elif exp_state == "over" and self.config.ENHANCE_ON_OVER:
            target_alpha = float(self.config.ENHANCE_OVER_ALPHA)
            target_beta = float(self.config.ENHANCE_OVER_BETA)
            self._enh_hold_until = max(self._enh_hold_until, now + float(self.config.ENHANCE_HOLD_SEC))
        else:
            # Normal: if within hold window, keep previous target
            if now < self._enh_hold_until:
                target_alpha, target_beta = self._enh_tgt_alpha, self._enh_tgt_beta
        # Blend current toward target
        blend = float(self.config.ENHANCE_BLEND_ALPHA)
        self._enh_tgt_alpha, self._enh_tgt_beta = target_alpha, target_beta
        self._enh_alpha = (1.0 - blend) * self._enh_alpha + blend * target_alpha
        self._enh_beta = (1.0 - blend) * self._enh_beta + blend * target_beta

        # Decide whether to run camera-side adjustments now
        run_adjust = False
        now2 = time.time()
        if self._detector_backend == "motion":
            # 1) Periodic adjust window with brief pause to avoid false detections
            if now2 - self._adjust_last_ts >= float(self.config.MOTION_ADJUST_PERIOD_SEC):
                self._adjust_last_ts = now2
                self._adjust_pause_until = now2 + float(self.config.MOTION_ADJUST_PAUSE_SEC)
                try:
                    self.detector.reset()
                except Exception:
                    pass
                self._seed_at_resume = True
                run_adjust = True
            # 2) While paused, continue adjustments to let controls converge
            elif now2 < self._adjust_pause_until:
                run_adjust = True
            else:
                run_adjust = False

            # 3) Failsafe: if still under/over and update intervals have elapsed,
            # perform an out-of-band single step with a micro-pause + reseed to
            # avoid comparing against pre-step baseline. This ensures continued
            # progress even if a prior window failed to trigger again.
            if not run_adjust and (self.state.exposure_state in ("under", "over")):
                need_ev = (
                    getattr(self, "_ev_last_update", 0.0) == 0.0 or
                    (now2 - getattr(self, "_ev_last_update", 0.0)) >= float(self.config.AE_EV_UPDATE_INTERVAL_SEC)
                ) and getattr(self.camera, "supports_ev", lambda: False)()
                need_gain = (
                    getattr(self, "_gain_last_update", 0.0) == 0.0 or
                    (now2 - getattr(self, "_gain_last_update", 0.0)) >= float(self.config.GAIN_UPDATE_INTERVAL_SEC)
                ) and getattr(self.camera, "supports_gain", lambda: False)()
                need_shutter = (
                    getattr(self, "_shutter_last_update", 0.0) == 0.0 or
                    (now2 - getattr(self, "_shutter_last_update", 0.0)) >= float(self.config.SHUTTER_UPDATE_INTERVAL_SEC)
                ) and getattr(self.camera, "supports_shutter", lambda: False)()
                if need_ev or need_gain or need_shutter:
                    # Use the configured pause length to keep semantics consistent
                    self._adjust_pause_until = now2 + float(self.config.MOTION_ADJUST_PAUSE_SEC)
                    try:
                        self.detector.reset()
                    except Exception:
                        pass
                    self._seed_at_resume = True
                    run_adjust = True

        if run_adjust:
            # Try to adjust camera EV-bias (Picamera2 only) to help AE converge
            self._maybe_adjust_ev(exp_state)
            # Try to adjust analogue gain (Picamera2) to brighten/darken
            self._maybe_adjust_gain(exp_state)
            # Try to adjust shutter time up to 1s if very dark
            self._maybe_adjust_shutter(exp_state)
        # Mirror current camera controls into state for UI/API
        self.state.ev_bias = float(getattr(self, "_ev_bias", 0.0))
        self.state.gain = float(getattr(self, "_gain_value", 0.0))
        self.state.shutter_us = int(getattr(self, "_shutter_us", 0))

    def _maybe_adjust_ev(self, exp_state: str) -> None:
        """Adapt camera exposure bias (EV) if supported and enabled.

        Args:
          exp_state: 'over' | 'under' | 'normal' | 'off'
        """
        if not self.config.AE_EV_ADAPT_ENABLE:
            return
        # Only Picamera2 implements set_ev; guard via duck-typing
        if not hasattr(self.camera, "set_ev") or not getattr(self.camera, "supports_ev")():
            return
        now = time.time()
        # Be defensive in case fields were not initialized yet
        last_update = getattr(self, "_ev_last_update", 0.0)
        if now - last_update < float(self.config.AE_EV_UPDATE_INTERVAL_SEC):
            return  # Too soon to update again

        ev = float(getattr(self, "_ev_bias", 0.0))
        if exp_state == "under":
            ev = min(self.config.AE_EV_MAX, ev + float(self.config.AE_EV_STEP))
        elif exp_state == "over":
            ev = max(self.config.AE_EV_MIN, ev - float(self.config.AE_EV_STEP))
        elif exp_state == "normal":
            # Nudge back toward zero
            step = float(self.config.AE_EV_RETURN_STEP)
            if ev > 0:
                ev = max(0.0, ev - step)
            elif ev < 0:
                ev = min(0.0, ev + step)
        else:
            return

        if abs(ev - getattr(self, "_ev_bias", 0.0)) < 1e-6:
            return  # No change
        if self.camera.set_ev(ev):
            self._ev_bias = ev
            self._ev_last_update = now
            # Reseed around significant camera control changes to avoid false triggers
            try:
                self._adjust_pause_until = now + float(self.config.MOTION_ADJUST_PAUSE_SEC)
                self.detector.reset()
                self._seed_at_resume = True
            except Exception:
                pass

    def _maybe_adjust_gain(self, exp_state: str) -> None:
        """Adapt analogue gain if supported and enabled.

        Args:
          exp_state: 'over' | 'under' | 'normal' | 'off'
        """
        if not self.config.GAIN_ADAPT_ENABLE:
            return
        if not hasattr(self.camera, "set_gain") or not getattr(self.camera, "supports_gain")():
            return
        now = time.time()
        last = getattr(self, "_gain_last_update", 0.0)
        if now - last < float(self.config.GAIN_UPDATE_INTERVAL_SEC):
            return

        g = float(getattr(self, "_gain_value", float(self.config.GAIN_MIN)))
        if exp_state == "under":
            g = min(self.config.GAIN_MAX, g + float(self.config.GAIN_STEP))
        elif exp_state == "over":
            g = max(self.config.GAIN_MIN, g - float(self.config.GAIN_STEP))
        elif exp_state == "normal":
            step = float(self.config.GAIN_RETURN_STEP)
            if g > 1.0:
                g = max(1.0, g - step)
            elif g < 1.0:
                g = min(1.0, g + step)
        else:
            return

        if abs(g - getattr(self, "_gain_value", 0.0)) < 1e-6:
            return
        if self.camera.set_gain(g):
            self._gain_value = g
            self._gain_last_update = now
            try:
                self._adjust_pause_until = now + float(self.config.MOTION_ADJUST_PAUSE_SEC)
                self.detector.reset()
                self._seed_at_resume = True
            except Exception:
                pass

    def _maybe_adjust_shutter(self, exp_state: str) -> None:
        """Adapt manual exposure time (shutter) for dim/bright scenes.

        Switches to manual exposure when under-exposed and ramps exposure time up
        to `SHUTTER_MAX_US`. When exposure returns to normal or bright, ramps
        down toward `SHUTTER_BASE_US` and re-enables AE when near base.
        """
        if not self.config.SHUTTER_ADAPT_ENABLE:
            return
        if not hasattr(self.camera, "set_shutter") or not getattr(self.camera, "supports_shutter")():
            return
        now = time.time()
        last = getattr(self, "_shutter_last_update", 0.0)
        if now - last < float(self.config.SHUTTER_UPDATE_INTERVAL_SEC):
            return

        cur = int(getattr(self, "_shutter_us", int(self.config.SHUTTER_BASE_US)))
        base = int(self.config.SHUTTER_BASE_US)
        changed = False

        if exp_state == "under":
            # Switch to manual exposure and increase shutter time
            target = min(self.config.SHUTTER_MAX_US, cur + int(self.config.SHUTTER_STEP_US))
            if target != cur:
                if self.camera.set_shutter(target):
                    self._shutter_us = target
                    self._manual_exposure = True
                    changed = True
                    try:
                        self._adjust_pause_until = now + float(self.config.MOTION_ADJUST_PAUSE_SEC)
                        self.detector.reset()
                        self._seed_at_resume = True
                    except Exception:
                        pass
        elif exp_state in ("normal", "over"):
            # Reduce shutter toward base; re-enable AE near base
            step = int(self.config.SHUTTER_RETURN_STEP_US)
            if cur > base:
                target = max(base, cur - step)
                if self.camera.set_shutter(target):
                    self._shutter_us = target
                    self._manual_exposure = True
                    changed = True
                    try:
                        self._adjust_pause_until = now + float(self.config.MOTION_ADJUST_PAUSE_SEC)
                        self.detector.reset()
                        self._seed_at_resume = True
                    except Exception:
                        pass
            # If near base, re-enable AE and stop manual control
            if abs(self._shutter_us - base) <= step:
                if hasattr(self.camera, "set_auto_exposure"):
                    if self.camera.set_auto_exposure(True):
                        self._manual_exposure = False

        if changed:
            self._shutter_last_update = now

    # NOIR colour-gain adjustment removed

    def _maybe_save_frame(self, frame: np.ndarray, detections) -> None:
        """Annotate and save the frame if save rate permits."""
        now = time.time()
        if now - self._last_saved_ts < self.config.SAVE_INTERVAL_SEC:
            return
        # Always build an annotated variant for SAVE_DIR when enabled
        annotated = frame.copy()
        for det in detections:
            x, y, w, h = det.bbox
            kind = getattr(det, "kind", "person")
            # BGR colors: red for person, cyan/yellowish for face, magenta for others
            if kind == "person":
                color = (0, 0, 255)
            elif kind == "face":
                color = (255, 200, 0)
            else:
                color = (255, 0, 255)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            # Label background and text
            label = f"{kind}"
            (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            bx1, by1 = x, max(0, y - th - baseline - 4)
            bx2, by2 = x + tw + 6, y
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), color, thickness=-1)
            cv2.putText(annotated, label, (x + 3, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        ts_str = time.strftime("%Y%m%d-%H%M%S")
        ms = int((now - int(now)) * 1000)
        filename = f"detect_{ts_str}_{ms:03d}.jpg"
        if self.config.SAVE_ANNOTATED_ON_DETECT:
            path = os.path.join(self.config.SAVE_DIR, filename)
            try:
                cv2.imwrite(path, annotated)
                self.state.saved_images_count += 1
                self._last_saved_ts = now
                self._enforce_retention(self.config.SAVE_DIR)
            except Exception:
                pass
        # Also save raw (no-annotation) copy if configured
        if self.config.SAVE_RAW_ON_DETECT:
            try:
                raw_path = os.path.join(self.config.SAVE_DIR_RAW, filename)
                cv2.imwrite(raw_path, frame)
                self._enforce_retention(self.config.SAVE_DIR_RAW)
            except Exception:
                pass

    def _enforce_retention(self, folder: Optional[str] = None) -> None:
        """Keep only the newest MAX_SAVED_IMAGES by deleting oldest files in a folder."""
        base = folder or self.config.SAVE_DIR
        try:
            files = [
                os.path.join(base, f)
                for f in os.listdir(base)
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
