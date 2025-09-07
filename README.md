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

Requirements
------------
- Raspberry Pi 3B with Raspberry Pi OS
- Raspberry Pi Camera Module connected and enabled
- Python 3.9+
- Packages: Flask, OpenCV, NumPy, (optionally) Picamera2

Install Dependencies
--------------------
Prefer system packages on Raspberry Pi to reduce build time:

    sudo apt update
    sudo apt install -y python3-opencv python3-flask python3-numpy

If using the modern camera stack (recommended on Bullseye/Bookworm):

    sudo apt install -y python3-picamera2

If Picamera2 is not available, the app will fallback to OpenCV V4L2 camera at `/dev/video0`.

Enable the Camera
-----------------
On newer Raspberry Pi OS versions, enable the camera in `raspi-config` and ensure `libcamera` stack is active. Picamera2 should then work without extra steps.

Run the App
-----------

    python3 main.py

Open the dashboard in a browser on your LAN:

    http://<pi-ip>:8000/

You should see:
- A live latest frame
- A red "HUMAN DETECTED" banner when people are detected
- A grid of recent captured images (saved in `data/captures/`)

Configuration
-------------
Tune behavior using environment variables (defaults shown). Only the motion detector is supported.

Camera
- `SC_CAMERA_BACKEND=auto` (or `picamera2`/`v4l2`)
- `SC_CAMERA_PROFILE=standard|noir` (NOIR always grayscale)
- `SC_FRAME_WIDTH=640` / `SC_FRAME_HEIGHT=480`
- `SC_CAPTURE_FPS=10`
- `SC_ROTATE_DEGREES=180` (0/90/180/270)

Motion detector
- `SC_DETECT_EVERY_N_FRAMES=5`: Run detector every Nth frame
- `SC_MOTION_DOWNSCALE=1.0`: 0.2–1.0 (lower = faster + smoother)
- `SC_MOTION_BLUR_KERNEL=3`: Odd blur kernel (3/5/7)
- `SC_MOTION_DELTA_THRESH=50`: Pixel change threshold (0–255)
- `SC_MOTION_DILATE_ITER=2`: Dilate iterations to close gaps
- `SC_MOTION_MIN_PIXELS=250`: Pixels changed (after downscale) to trigger
- Motion-aware exposure cadence: `SC_MOTION_ADJUST_PERIOD_SEC=180.0`, `SC_MOTION_ADJUST_PAUSE_SEC=3.0`

Saving
- `SC_SAVE_DIR=data/captures`: Annotated output folder
- `SC_SAVE_DIR_RAW=data/captures_raw`: Raw (no overlays) output folder
- `SC_SAVE_ANNOTATED_ON_DETECT=1` / `SC_SAVE_RAW_ON_DETECT=1`
- `SC_SAVE_INTERVAL_SEC=1.0`
- `SC_MAX_SAVED_IMAGES=2000`

Adaptive exposure (Picamera2)
- `SC_ADAPTIVE_SENSITIVITY=1`
- `SC_EXP_BRIGHT_MEAN=200` / `SC_EXP_DARK_MEAN=40` / `SC_EXP_DARK_MEAN_EXIT=50`
- `SC_EXP_EMA_ALPHA=0.35`, `SC_EXP_HIGH_CLIP_FRAC=0.05`, `SC_EXP_LOW_CLIP_FRAC=0.05`
- Frame enhancement: `SC_ENHANCE_UNDER_ALPHA=2.5`, `SC_ENHANCE_UNDER_BETA=20`, blending/hold via `SC_ENHANCE_BLEND_ALPHA`, `SC_ENHANCE_HOLD_SEC`
- EV: `SC_AE_EV_ADAPT_ENABLE=1`, `SC_AE_EV_MIN`, `SC_AE_EV_MAX`, `SC_AE_EV_STEP`, `SC_AE_EV_RETURN_STEP`, `SC_AE_EV_UPDATE_INTERVAL_SEC`
- Gain: `SC_GAIN_ADAPT_ENABLE=1`, `SC_GAIN_MIN`, `SC_GAIN_MAX`, `SC_GAIN_STEP`, `SC_GAIN_RETURN_STEP`, `SC_GAIN_UPDATE_INTERVAL_SEC`
- Shutter: `SC_SHUTTER_ADAPT_ENABLE=0|1`, `SC_SHUTTER_MIN_US`, `SC_SHUTTER_MAX_US`, `SC_SHUTTER_STEP_US`, `SC_SHUTTER_RETURN_STEP_US`, `SC_SHUTTER_BASE_US`, `SC_SHUTTER_UPDATE_INTERVAL_SEC`

Notes and Tips
--------------
- Performance: The HOG detector is CPU-heavy. Defaults are tuned for Pi 3B. Lower resolution or raise `SC_DETECT_EVERY_N_FRAMES` for more headroom.
- Camera backend: Picamera2 is preferred. If it’s not available, ensure `/dev/video0` is exposed (e.g., `libcamera-vid --inline --width 640 --height 480 --framerate 10 --codec yuv420 --listen &` can provide a v4l2 loopback if configured) or use the legacy stack if your OS provides it.
- Storage: Images can fill the SD card. The app enforces `SC_MAX_SAVED_IMAGES`; adjust to your capacity.
- Service: To run on boot, wrap `python3 /path/to/main.py` in a `systemd` service.
- Startup: Flask now starts even if the camera backend is slow or failing; set `SC_CAMERA_BACKEND=v4l2` to force OpenCV/V4L2 if Picamera2 causes startup issues.
 - NOIR (IR) cameras: Colors are unreliable under IR illumination. Prefer `SC_NOIR_RENDER_MODE=mono` for clear grayscale images and more stable detection. If you need color, set `SC_NOIR_RENDER_MODE=correct` and tune `SC_NOIR_COLOUR_GAIN_R/B`.

systemd Service (Auto-start on Boot)
------------------------------------
Quick one-shot setup:

    sudo bash scripts/setup_raspi_env.sh \
      --user pi \
      --project-dir /home/pi/raspi-security-cam \
      --port 8000 \
      --active-windows "22:00-06:00" \
      --allow-ufw any

This script installs dependencies, sets up the systemd unit, creates the capture directory, writes `/etc/default/raspi-security-cam`, optionally opens UFW, and starts the service.

Manual steps (alternative):
1) Copy the unit file and edit paths/user:

    sudo cp packaging/systemd/raspi-security-cam.service /etc/systemd/system/
    sudoedit /etc/systemd/system/raspi-security-cam.service

   - Set `User=` to the user that should run it (e.g., `pi`).
   - Set `WorkingDirectory=` to the project path (e.g., `/home/pi/raspi-security-cam`).

2) Optional: configure environment via `/etc/default`:

    sudo cp packaging/systemd/raspi-security-cam.env.example /etc/default/raspi-security-cam
    sudoedit /etc/default/raspi-security-cam

3) Enable and start:

    sudo systemctl daemon-reload
    sudo systemctl enable raspi-security-cam
    sudo systemctl start raspi-security-cam
    systemctl status raspi-security-cam --no-pager

4) Logs:

    journalctl -u raspi-security-cam -f

Scheduling
----------
- Set `SC_ACTIVE_WINDOWS` to arm the detector only during specific daily times. Examples:
  - Nightly: `SC_ACTIVE_WINDOWS=22:00-06:00`
  - Multiple windows: `SC_ACTIVE_WINDOWS=22:00-06:00,12:30-13:30`
- When disarmed, frames still update on the dashboard but detection/saving are paused. The header shows Armed/Disarmed.

License
-------
No license specified; for personal use.

Updated Configuration (Motion-only + NOIR Mono)
-----------------------------------------------
The app now uses only the motion detector (frame differencing). HOG/face and background subtraction detectors have been removed to simplify and improve performance on Raspberry Pi 3B. When using a NOIR camera, frames are always rendered in grayscale (no color mode).

Key settings
- Motion detector (tuning):
  - `SC_DETECT_EVERY_N_FRAMES` (default 5): Run detection every Nth frame to reduce CPU
  - `SC_MOTION_DOWNSCALE` (0.2–1.0, default 1.0)
  - `SC_MOTION_BLUR_KERNEL` (odd, default 3)
  - `SC_MOTION_DELTA_THRESH` (default 50)
  - `SC_MOTION_DILATE_ITER` (default 2)
  - `SC_MOTION_MIN_PIXELS` (default 250)
- Saving:
  - `SC_SAVE_DIR`: annotated output folder
  - `SC_SAVE_DIR_RAW`: raw (no overlays) output folder
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

    sudo apt update && sudo apt full-upgrade -y
    sudo reboot

3) Enable the camera (libcamera stack)
- `sudo raspi-config` → Interface Options → I2C → Enable (recommended)
- Legacy Camera should remain DISABLED on Bookworm

4) Install packages

    sudo apt update
    sudo apt install -y python3-opencv python3-flask python3-numpy python3-picamera2 ufw
    # Optional diagnostics
    sudo apt install -y rpicam-apps v4l-utils

5) Get the app onto your Pi

    cd ~
    mkdir -p ~/work && cd ~/work
    # If using git (replace with your origin):
    # git clone <your-repo-url> utl-secam
    # cd utl-secam
    # Or cd into the directory you copied.

6) One-shot setup (recommended)

    cd /path/to/utl-secam
    sudo bash scripts/setup_raspi_env.sh \
      --user $USER \
      --project-dir $(pwd) \
      --port 8000 \
      --active-windows "22:00-06:00" \
      --allow-ufw 192.168.10.0/24   # your LAN (or 'any' or 'skip')

Notes:
- Pass your actual username with `--user` (default pi). The script is idempotent.
- The service is named `raspi-security-cam`.

7) Verify service + dashboard

    sudo systemctl status raspi-security-cam --no-pager
    sudo ss -lntp | grep :8000 || true
    # In a browser on LAN: http://<pi-ip>:8000/

Endpoints
---------
- Latest frame: `http://<pi-ip>:8000/latest.jpg`
- MJPEG stream: `http://<pi-ip>:8000/stream.mjpg`
- JSON state: `http://<pi-ip>:8000/api/state` (includes exposure/adaptive telemetry)

8) Configure behavior
Edit the service env:

```
sudoedit /etc/default/raspi-security-cam
# SC_HOST=0.0.0.0
# SC_PORT=8000
# SC_CAMERA_BACKEND=picamera2   # or v4l2 or auto
# SC_FRAME_WIDTH=640
# SC_FRAME_HEIGHT=480
# SC_CAPTURE_FPS=5
# SC_DETECT_EVERY_N_FRAMES=2
# SC_SAVE_DIR=/path/to/data/captures
# SC_ACTIVE_WINDOWS="22:00-06:00"
# Adaptive sensitivity (on by default):
# SC_ADAPTIVE_SENSITIVITY=1
# SC_EXP_BRIGHT_MEAN=200
# SC_EXP_DARK_MEAN=40
# SC_EXP_HIGH_CLIP_FRAC=0.05
# SC_EXP_LOW_CLIP_FRAC=0.05
# SC_ADAPT_HIT_THRESHOLD_DELTA=0.5
# SC_ADAPT_MIN_SIZE_SCALE=1.2
# SC_ADAPT_DETECT_STRIDE_SCALE=2.0
```

Apply changes:

    sudo systemctl restart raspi-security-cam

9) Firewall (UFW)

    sudo ufw allow from 192.168.10.0/24 to any port 8000 proto tcp
    sudo ufw status

Alternative: SSH tunnel instead of opening the port:

    ssh -L 8000:localhost:8000 <user>@<pi-ip>
    # then open http://localhost:8000

10) Camera diagnostics
If frames stay at 0, test the camera outside the app:

    sudo systemctl stop raspi-security-cam
    rpicam-hello -n -t 2000
    v4l2-ctl --list-devices
    dmesg | grep -i -E 'imx|ov|unicam|camera'

If “no cameras available”, reseat the CSI ribbon and, if you know the model, force the overlay in `/boot/firmware/config.txt`:
- `dtoverlay=ov5647` (v1)
- `dtoverlay=imx219` (v2)
- `dtoverlay=imx477` (HQ)
- `dtoverlay=imx708` (v3)

Then reboot and retest:

    sudo systemctl start raspi-security-cam

11) Service management

    sudo systemctl start raspi-security-cam
    sudo systemctl stop raspi-security-cam
    sudo systemctl restart raspi-security-cam
    sudo journalctl -u raspi-security-cam -f

12) Where files live
- Code: your project directory (e.g., `/home/<user>/work/utl-secam`)
- Captures: `data/captures/` (configurable via `SC_SAVE_DIR`)
- Systemd unit: `/etc/systemd/system/raspi-security-cam.service`
- Service env: `/etc/default/raspi-security-cam`

13) Uninstall / disable

    sudo systemctl disable --now raspi-security-cam
    sudo rm /etc/systemd/system/raspi-security-cam.service
    sudo rm /etc/default/raspi-security-cam
    sudo systemctl daemon-reload

Optionally remove the project folder and capture directory.

14) Security notes
- The dashboard has no authentication; avoid exposing to the internet.
- Restrict UFW to LAN or use SSH/VPN; consider reverse proxy + auth on port 80.

15) Performance tips (Pi 3B)
- 640x480 @ 5 FPS is a good balance.
- `SC_DETECT_EVERY_N_FRAMES=2` cuts CPU while staying responsive.
- Adaptive sensitivity (default on) auto-tunes detection in poor lighting.
