Raspberry Pi Security Camera (Python)
====================================

Features
--------
- Human detection using OpenCV HOG people detector
- Saves many annotated pictures when a human is detected
- Simple Flask dashboard with a warning banner, live frame, and recent gallery
- Lightweight and configurable for Raspberry Pi 3B
- Optional daily arming schedule (e.g., 22:00-06:00)
- Adaptive sensitivity: detects over/under exposure and auto-tunes detection thresholds to reduce false positives and CPU when scenes are too bright/dark.

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
Tune behavior using environment variables (defaults shown):

- `SC_FRAME_WIDTH=640` / `SC_FRAME_HEIGHT=480`: Capture resolution
- `SC_CAPTURE_FPS=10`: Target FPS
- `SC_DETECT_EVERY_N_FRAMES=2`: Run detector every Nth frame
- `SC_SAVE_DIR=data/captures`: Directory for saved images
- `SC_SAVE_INTERVAL_SEC=1.0`: Min seconds between saved frames
- `SC_MAX_SAVED_IMAGES=2000`: Retention limit (oldest deleted)
- `SC_ALERT_COOLDOWN_SEC=10.0`: How long to keep alert after last detection
- `SC_GALLERY_LATEST_COUNT=12`: Images shown in dashboard gallery
- `SC_HOST=0.0.0.0` / `SC_PORT=8000`: Server bind
- `SC_DEBUG=0`: Set `1` to enable Flask debug
- `SC_ACTIVE_WINDOWS=""`: Comma-separated daily windows to arm detection, e.g., `22:00-06:00` or `22:00-06:00,12:30-13:30`. Empty means always armed. Times use the Pi's local time.
- `SC_CAMERA_BACKEND=auto`: Choose `picamera2`, `v4l2`, or `auto`.
- Adaptive sensitivity:
  - `SC_ADAPTIVE_SENSITIVITY=1`: Enable exposure-aware tuning
  - `SC_EXP_BRIGHT_MEAN=200` / `SC_EXP_DARK_MEAN=40`: Mean brightness cutoffs
  - `SC_EXP_EMA_ALPHA=0.35`: Exposure smoothing factor (higher reacts faster)
  - `SC_EXP_HIGH_CLIP_FRAC=0.05` / `SC_EXP_LOW_CLIP_FRAC=0.05`: Fraction of pixels near 255/0 to flag clipping
  - `SC_ADAPT_HIT_THRESHOLD_DELTA=0.5`: Extra HOG hit threshold when exposure is poor
  - `SC_ADAPT_MIN_SIZE_SCALE=1.2`: Scale min person size under poor exposure
  - `SC_ADAPT_DETECT_STRIDE_SCALE=2.0`: Multiply detection cadence under poor exposure
 - Optional frame enhancement (applied when exposure is poor):
   - `SC_ENHANCE_ON_UNDER=1`, `SC_ENHANCE_UNDER_ALPHA=1.5`, `SC_ENHANCE_UNDER_BETA=20`
   - `SC_ENHANCE_ON_OVER=1`, `SC_ENHANCE_OVER_ALPHA=0.85`, `SC_ENHANCE_OVER_BETA=-10`
 - Camera-side auto-exposure EV-bias (Picamera2 only):
   - `SC_AE_EV_ADAPT_ENABLE=1`
   - `SC_AE_EV_MIN=-2.0` / `SC_AE_EV_MAX=2.0`: EV clamp
   - `SC_AE_EV_STEP=0.2`: Step toward brighter/darker when under/over
   - `SC_AE_EV_RETURN_STEP=0.1`: Step back toward 0 when normal
   - `SC_AE_EV_UPDATE_INTERVAL_SEC=1.0`: Min seconds between EV changes

Notes and Tips
--------------
- Performance: The HOG detector is CPU-heavy. Defaults are tuned for Pi 3B. Lower resolution or raise `SC_DETECT_EVERY_N_FRAMES` for more headroom.
- Camera backend: Picamera2 is preferred. If it’s not available, ensure `/dev/video0` is exposed (e.g., `libcamera-vid --inline --width 640 --height 480 --framerate 10 --codec yuv420 --listen &` can provide a v4l2 loopback if configured) or use the legacy stack if your OS provides it.
- Storage: Images can fill the SD card. The app enforces `SC_MAX_SAVED_IMAGES`; adjust to your capacity.
- Service: To run on boot, wrap `python3 /path/to/main.py` in a `systemd` service.
- Startup: Flask now starts even if the camera backend is slow or failing; set `SC_CAMERA_BACKEND=v4l2` to force OpenCV/V4L2 if Picamera2 causes startup issues.

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
