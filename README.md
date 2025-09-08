Raspberry Pi Security Camera (Python)
====================================

Features
--------
- Motion detection (frame differencing), tuned for Raspberry Pi 3B
- Saves annotated captures (with boxes) and/or raw copies (no overlays)
- Simple Flask dashboard with a warning banner, live view, and recent gallery
- Lightweight and configurable for Raspberry Pi 3B
- Optional daily arming schedule (e.g., 22:00-06:00)
- Adaptive exposure control with motion-aware cadence to avoid false triggers
- Picamera2 YUV pipeline with luma-based detection for lower CPU and better IR consistency
- Autofocus controls for Pi Camera v3 (IMX708): auto/continuous/manual with optional focus lock for night
- Robust motion detector: noise-adaptive thresholding, optional morphological opening, and static ignore mask support

Requirements
------------
- Raspberry Pi 3B with Raspberry Pi OS
- Raspberry Pi Camera Module connected and enabled
- Python 3.9+
- Packages: Flask, OpenCV, NumPy, (optionally) Picamera2

Install Dependencies
--------------------
Prefer system packages on Raspberry Pi to reduce build time:

```
sudo apt update
sudo apt install -y python3-opencv python3-flask python3-numpy
```

If using the modern camera stack (recommended on Bullseye/Bookworm):

```
sudo apt install -y python3-picamera2
```

If Picamera2 is not available, the app will fallback to OpenCV V4L2 camera at `/dev/video0`.

Enable the Camera
-----------------
On newer Raspberry Pi OS versions, enable the camera in `raspi-config` and ensure `libcamera` stack is active. Picamera2 should then work without extra steps.

Run the App
-----------

```
python3 main.py
```

Open the dashboard in a browser on your LAN:

```
http://<pi-ip>:8000/
```

You should see:
- A live latest frame
- A red "MOTION DETECTED" alert when motion is detected
- A grid of recent captured images (saved in `data/captures/`)

Configuration
-------------
Tune behavior using environment variables (defaults shown). Only the motion detector is supported.

Camera
- `SC_CAMERA_BACKEND=auto` (or `picamera2`/`v4l2`) — `auto` tries Picamera2 first, then falls back to V4L2 (`/dev/video0`).
- `SC_CAMERA_PROFILE=standard|noir` (default `noir`; NOIR always grayscale)
- `SC_FRAME_WIDTH=320` / `SC_FRAME_HEIGHT=240`
- `SC_CAPTURE_FPS=5`
- `SC_ROTATE_DEGREES=180` (0/90/180/270)
- `SC_USE_YUV=1|0` (default `1`, Picamera2 only): when `1`, capture in YUV420 and use luma (Y) for detection for stable IR behavior; when `0`, use RGB888.
- Autofocus (Pi Camera v3 via Picamera2)
  - `SC_AF_MODE=auto|continuous|manual` (default `auto`). Choose `manual` to lock focus.
  - `SC_AF_LENS_POSITION=<float>` Lens position when `manual` is used (and for NOIR lock when enabled). Set `-1` to skip.
  - `SC_AF_LOCK_ON_NOIR=1|0` (default `1`). If NOIR profile and `SC_AF_LENS_POSITION>=0`, focus is locked to avoid hunting at night.

Motion detector
- `SC_DETECT_EVERY_N_FRAMES=1`: Run detector every Nth frame
- `SC_MOTION_DOWNSCALE=1.0`: 0.2–1.0 (lower = faster + smoother)
- `SC_MOTION_BLUR_KERNEL=3`: Odd blur kernel (3/5/7)
- `SC_MOTION_DELTA_THRESH=50`: Pixel change threshold (0–255)
- `SC_MOTION_DILATE_ITER=2`: Dilate iterations to close gaps
- Noise handling and masks
  - `SC_MOTION_OPEN_ITER=1`: Morphological opening iterations after thresholding (0 disables) to remove speckles.
  - `SC_MOTION_NOISE_ADAPT=1`: Increase threshold by `K * sigma` measured over a small center ROI.
  - `SC_MOTION_NOISE_K=1.5`: Multiplier for ROI standard deviation.
  - `SC_MOTION_NOISE_ROI_FRAC=0.2`: ROI fraction (e.g., 0.2 = center 20% by 20%).
  - `SC_MOTION_MASK_PATH=/path/to/mask.png`: Static ignore mask (white = detect, black = ignore). Auto-resized.
- `SC_MOTION_MIN_PIXELS` (default = 3% of frame area): Pixels changed (after downscale) to trigger. At 320×240 this is 2304.
- Motion-aware exposure cadence: `SC_MOTION_ADJUST_PERIOD_SEC=120.0`, `SC_MOTION_ADJUST_PAUSE_SEC=1.0`

Saving
- `SC_SAVE_DIR=data/captures`: Annotated output folder
- `SC_SAVE_DIR_RAW=data/captures_raw`: Raw (no overlays) output folder
- `SC_SAVE_ON_DETECT=1`: Master switch to save on detections
- `SC_SAVE_ANNOTATED_ON_DETECT=1` / `SC_SAVE_RAW_ON_DETECT=1`
- `SC_SAVE_INTERVAL_SEC=0.5` (default raised from 0.05 to reduce SD wear/CPU)
- `SC_MAX_SAVED_IMAGES=1000`
Notes:
- The dashboard shows annotated images. Clicking a thumbnail opens the raw image at `/captures_raw/<file>` when available; it falls back to the annotated copy.

Adaptive exposure (Picamera2)
- `SC_ADAPTIVE_SENSITIVITY=1`
- `SC_EXP_BRIGHT_MEAN=200` / `SC_EXP_DARK_MEAN=50` / `SC_EXP_DARK_MEAN_EXIT=60`
- `SC_EXP_EMA_ALPHA=0.35`, `SC_EXP_HIGH_CLIP_FRAC=0.05`, `SC_EXP_LOW_CLIP_FRAC=0.03`
- Frame enhancement: `SC_ENHANCE_UNDER_ALPHA=2.5`, `SC_ENHANCE_UNDER_BETA=20`, `SC_ENHANCE_BLEND_ALPHA=0.4`, `SC_ENHANCE_HOLD_SEC=2.0`
- Over-exposure handling: `SC_ENHANCE_ON_OVER=1`, `SC_ENHANCE_OVER_ALPHA=0.85`, `SC_ENHANCE_OVER_BETA=-10`
- EV: `SC_AE_EV_ADAPT_ENABLE=1`, `SC_AE_EV_MIN`, `SC_AE_EV_MAX`, `SC_AE_EV_STEP`, `SC_AE_EV_RETURN_STEP`, `SC_AE_EV_UPDATE_INTERVAL_SEC`
- Gain: `SC_GAIN_ADAPT_ENABLE=1`, `SC_GAIN_MIN`, `SC_GAIN_MAX`, `SC_GAIN_STEP`, `SC_GAIN_RETURN_STEP`, `SC_GAIN_UPDATE_INTERVAL_SEC`
- Shutter: `SC_SHUTTER_ADAPT_ENABLE=0|1` (default `0`), `SC_SHUTTER_MIN_US`, `SC_SHUTTER_MAX_US`, `SC_SHUTTER_STEP_US`, `SC_SHUTTER_RETURN_STEP_US`, `SC_SHUTTER_BASE_US`, `SC_SHUTTER_UPDATE_INTERVAL_SEC`
- Reseed baseline after idle gaps: `SC_SEED_AFTER_IDLE_SEC=3.0`
Notes:
- These controls require Picamera2 and hardware support. When running via V4L2/USB webcams, these settings are ignored safely.

Dashboard and server
- `SC_HOST=0.0.0.0` (bind address), `SC_PORT=8000`, `SC_DEBUG=0`
- `SC_GALLERY_LATEST_COUNT=9`: Number of recent images shown on the dashboard
- `SC_ALERT_COOLDOWN_SEC=10.0`: How long the alert banner stays on after motion

Notes and Tips
--------------
- Performance: Defaults are tuned for Pi 3B. If CPU is high, lower resolution, reduce FPS, or raise `SC_DETECT_EVERY_N_FRAMES` for more headroom.
- Camera backend: Picamera2 is preferred. If it’s not available, ensure `/dev/video0` is exposed (e.g., `libcamera-vid --inline --width 640 --height 480 --framerate 10 --codec yuv420 --listen &` can provide a V4L2 loopback if configured; requires the `v4l2loopback` kernel module) or use the legacy stack if your OS provides it.
- Storage: Images can fill the SD card. The app enforces `SC_MAX_SAVED_IMAGES`; adjust to your capacity.
- Service: To run on boot, wrap `python3 /path/to/main.py` in a `systemd` service.
- Startup: Flask now starts even if the camera backend is slow or failing; set `SC_CAMERA_BACKEND=v4l2` to force OpenCV/V4L2 if Picamera2 causes startup issues.
- NOIR (IR) cameras: Under IR illumination, colors are unreliable. In `noir` profile the app renders grayscale always and forces neutral colour gains (1.0,1.0) with AWB off for stable luma.
- Picamera2 YUV: The camera runs in YUV420; detection prefers the Y plane to avoid extra conversions and improve consistency in low light. BGR conversion happens only for UI/JPEG.
- Streaming: MJPEG quality is set lower (60) to reduce CPU/bandwidth on low-power Pis.

systemd Service (Auto-start on Boot)
------------------------------------
Quick one-shot setup:

```
sudo bash scripts/setup_raspi_env.sh \
  --user pi \
  --project-dir /home/pi/raspi-security-cam \
  --port 8000 \
  --active-windows "22:00-06:00" \
  --allow-ufw any
```

This script installs dependencies, sets up the systemd unit, creates the capture directory, writes `/etc/default/raspi-security-cam`, optionally opens UFW, and starts the service.

Manual steps (alternative):
1) Copy the unit file and edit paths/user:

```
sudo cp packaging/systemd/raspi-security-cam.service /etc/systemd/system/
sudoedit /etc/systemd/system/raspi-security-cam.service
```

   - Set `User=` to the user that should run it (e.g., `pi`).
   - Set `WorkingDirectory=` to the project path (e.g., `/home/pi/raspi-security-cam`).

2) Optional: configure environment via `/etc/default`:

```
sudo cp packaging/systemd/raspi-security-cam.env.example /etc/default/raspi-security-cam
sudoedit /etc/default/raspi-security-cam
```

3) Enable and start:

```
sudo systemctl daemon-reload
sudo systemctl enable raspi-security-cam
sudo systemctl start raspi-security-cam
systemctl status raspi-security-cam --no-pager
```

4) Logs:

```
journalctl -u raspi-security-cam -f
```

Scheduling
----------
- Set `SC_ACTIVE_WINDOWS` to arm the detector only during specific daily times. Examples:
  - Nightly: `SC_ACTIVE_WINDOWS=22:00-06:00`
  - Multiple windows: `SC_ACTIVE_WINDOWS=22:00-06:00,12:30-13:30`
- When disarmed, frames still update on the dashboard but detection/saving are paused. The header shows Armed/Disarmed.
Notes:
- Windows wrap past midnight when the end time is earlier than the start (e.g., `22:00-06:00`).
- The end of each window is exclusive; start is inclusive.
- An empty `SC_ACTIVE_WINDOWS` means “always armed”.
- The schedule uses the device’s local time.

License
-------
No license specified; for personal use.

Updated Configuration (Motion-only + NOIR Mono)
-----------------------------------------------
The app now uses only the motion detector (frame differencing). HOG/face and background subtraction detectors have been removed to simplify and improve performance on Raspberry Pi 3B. When using a NOIR camera, frames are always rendered in grayscale (no color mode).

Key settings
- Motion detector (tuning):
  - `SC_DETECT_EVERY_N_FRAMES` (default 1): Run detection every Nth frame to reduce CPU
  - `SC_MOTION_DOWNSCALE` (0.2–1.0, default 1.0)
  - `SC_MOTION_BLUR_KERNEL` (odd, default 3)
  - `SC_MOTION_DELTA_THRESH` (default 50)
  - `SC_MOTION_DILATE_ITER` (default 2)
  - `SC_MOTION_MIN_PIXELS` (default = 3% of frame area; e.g., 2304 at 320×240)
- Saving:
  - `SC_SAVE_DIR`: annotated output folder
  - `SC_SAVE_DIR_RAW`: raw (no overlays) output folder
  - `SC_SAVE_ON_DETECT=1`: master on/off for saving when motion is detected
  - `SC_SAVE_ANNOTATED_ON_DETECT=1` / `SC_SAVE_RAW_ON_DETECT=1`
- Adaptive exposure (Picamera2):
  - `SC_ADAPTIVE_SENSITIVITY=1`, `SC_EXP_BRIGHT_MEAN`, `SC_EXP_DARK_MEAN`, `SC_EXP_DARK_MEAN_EXIT`, `SC_EXP_EMA_ALPHA`
  - EV/Gain/Shutter knobs: `SC_AE_EV_*`, `SC_GAIN_*`, `SC_SHUTTER_*`
  - Motion-aware cadence: `SC_MOTION_ADJUST_PERIOD_SEC`, `SC_MOTION_ADJUST_PAUSE_SEC`
- NOIR profile:
  - `SC_CAMERA_PROFILE=standard|noir` (NOIR always grayscale; no color settings)

Quickstart (Fresh Install)
-------------------------
This step-by-step guide covers a clean Raspberry Pi setup through a working, auto-starting camera app.

1) Hardware + OS
- Raspberry Pi 3B (defaults tuned for 3B; others work)
- Raspberry Pi Camera Module (v1/ov5647, v2/imx219, HQ/imx477, or v3/imx708)
- Raspberry Pi OS Bookworm
- LAN connectivity

2) Update OS

```
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

3) Enable the camera (libcamera stack)
- On Raspberry Pi OS Bookworm, the libcamera stack is active by default; no changes are usually required.
- Do NOT enable the “Legacy Camera” option on Bookworm.
- I2C is optional and unrelated to the camera stack; enable it only if you need I2C peripherals.

4) Install packages

```
sudo apt update
sudo apt install -y python3-opencv python3-flask python3-numpy python3-picamera2 ufw
# Optional diagnostics
sudo apt install -y rpicam-apps v4l-utils
```

5) Get the app onto your Pi
    ```
    cd ~
    mkdir -p ~/work && cd ~/work
    # If using git (replace with your origin):
    # git clone <your-repo-url> utl-secam
    # cd utl-secam
    # Or cd into the directory you copied.
    ```

6) One-shot setup (recommended)
    ```
    cd /path/to/utl-secam
    sudo bash scripts/setup_raspi_env.sh \
      --user $USER \
      --project-dir $(pwd) \
      --port 8000 \
      --active-windows "22:00-06:00" \
      --allow-ufw 192.168.10.0/24   # your LAN (or 'any' or 'skip')
    ```

Notes:
- Pass your actual username with `--user` (default pi). The script is idempotent.
- The service is named `raspi-security-cam`.

7) Verify service + dashboard

```
sudo systemctl status raspi-security-cam --no-pager
sudo ss -lntp | grep :8000 || true
# In a browser on LAN: http://<pi-ip>:8000/
```

Endpoints
---------
- Latest frame: `http://<pi-ip>:8000/latest.jpg`
- MJPEG stream: `http://<pi-ip>:8000/stream.mjpg`
- JSON state: `http://<pi-ip>:8000/api/state` (includes exposure/adaptive telemetry)
- Captured image (annotated): `http://<pi-ip>:8000/captures/<filename>`
- Captured image (raw): `http://<pi-ip>:8000/captures_raw/<filename>`
Note: `/captures_raw/<file>` serves raw images, falling back to annotated if the raw copy was not saved.

8) Configure behavior
Edit the service env:

```
sudoedit /etc/default/raspi-security-cam
# SC_HOST=0.0.0.0
# SC_PORT=8000
# SC_CAMERA_BACKEND=picamera2   # or v4l2 or auto
# SC_FRAME_WIDTH=320
# SC_FRAME_HEIGHT=240
# SC_CAPTURE_FPS=5
# SC_DETECT_EVERY_N_FRAMES=1
# SC_SAVE_DIR=/path/to/data/captures
# SC_ACTIVE_WINDOWS="22:00-06:00"
# Adaptive sensitivity (on by default):
# SC_ADAPTIVE_SENSITIVITY=1
# SC_EXP_BRIGHT_MEAN=200
# SC_EXP_DARK_MEAN=50
# SC_EXP_DARK_MEAN_EXIT=60
# SC_EXP_HIGH_CLIP_FRAC=0.05
# SC_EXP_LOW_CLIP_FRAC=0.03
# (Legacy compatibility; not used by motion-only detector)
# SC_ADAPT_HIT_THRESHOLD_DELTA=0.5
# SC_ADAPT_MIN_SIZE_SCALE=1.2
# SC_ADAPT_DETECT_STRIDE_SCALE=2.0
```

Apply changes:

```
sudo systemctl restart raspi-security-cam
```

9) Firewall (UFW)

```
sudo ufw allow from 192.168.10.0/24 to any port 8000 proto tcp
sudo ufw status
```

Alternative: SSH tunnel instead of opening the port:

```
ssh -L 8000:localhost:8000 <user>@<pi-ip>
# then open http://localhost:8000
```

10) Camera diagnostics
If frames stay at 0, test the camera outside the app:

```
sudo systemctl stop raspi-security-cam
rpicam-hello -n -t 2000
v4l2-ctl --list-devices
dmesg | grep -i -E 'imx|ov|unicam|camera'
```

If “no cameras available”, reseat the CSI ribbon and, if you know the model, force the overlay in `/boot/firmware/config.txt`:
- `dtoverlay=ov5647` (v1)
- `dtoverlay=imx219` (v2)
- `dtoverlay=imx477` (HQ)
- `dtoverlay=imx708` (v3)

Then reboot and retest:

```
sudo systemctl start raspi-security-cam
```

11) Service management

```
sudo systemctl start raspi-security-cam
sudo systemctl stop raspi-security-cam
sudo systemctl restart raspi-security-cam
sudo journalctl -u raspi-security-cam -f
```

12) Where files live
- Code: your project directory (e.g., `/home/<user>/work/utl-secam`)
- Captures: `data/captures/` (configurable via `SC_SAVE_DIR`)
- Systemd unit: `/etc/systemd/system/raspi-security-cam.service`
- Service env: `/etc/default/raspi-security-cam`

13) Uninstall / disable

```
sudo systemctl disable --now raspi-security-cam
sudo rm /etc/systemd/system/raspi-security-cam.service
sudo rm /etc/default/raspi-security-cam
sudo systemctl daemon-reload
```

Optionally remove the project folder and capture directory.

14) Security notes
- The dashboard has no authentication; avoid exposing to the internet.
- Restrict UFW to LAN or use SSH/VPN; consider reverse proxy + auth on port 80.

15) Performance tips (Pi 3B)
- 640x480 @ 5 FPS is a good balance.
- `SC_DETECT_EVERY_N_FRAMES=2` cuts CPU while staying responsive.
- Adaptive sensitivity (default on) auto-tunes detection in poor lighting.
- For night-only installs: consider `SC_AF_MODE=manual`, set a lens position that matches your typical subject distance, and enable an IR illuminator.

Low-Light and Night Behavior
----------------------------
- Autofocus at night: AF can hunt in dim scenes. Use `SC_AF_MODE=manual` and a sensible `SC_AF_LENS_POSITION` for your target distance, or keep `auto/continuous` during day and enable `SC_AF_LOCK_ON_NOIR=1` so focus locks when using the NOIR profile.
- Ignore masks: Create a mask image matching your camera aspect (white = detect, black = ignore). Point `SC_MOTION_MASK_PATH` to it. The app resizes it to the working resolution (after any internal downscale). Make the mask using a snapshot from `/latest.jpg` to ensure rotation/orientation matches.
- Noise handling: If the scene has heavy sensor snow at night, enable `SC_MOTION_OPEN_ITER` (e.g., 1–2) and leave `SC_MOTION_NOISE_ADAPT=1` so the threshold scales with noise.
- Reseeding: The app automatically reseeds the motion baseline (a) after configured camera adjustments, (b) after successful EV/gain/shutter changes, and (c) after idle/no-frame gaps controlled by `SC_SEED_AFTER_IDLE_SEC`. This prevents false positives from global brightness jumps.
