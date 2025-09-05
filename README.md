Raspberry Pi Security Camera (Python)
====================================

Features
--------
- Human detection using OpenCV HOG people detector
- Saves many annotated pictures when a human is detected
- Simple Flask dashboard with a warning banner, live frame, and recent gallery
- Lightweight and configurable for Raspberry Pi 3B
- Optional daily arming schedule (e.g., 22:00-06:00)

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

Notes and Tips
--------------
- Performance: The HOG detector is CPU-heavy. Defaults are tuned for Pi 3B. Lower resolution or raise `SC_DETECT_EVERY_N_FRAMES` for more headroom.
- Camera backend: Picamera2 is preferred. If it’s not available, ensure `/dev/video0` is exposed (e.g., `libcamera-vid --inline --width 640 --height 480 --framerate 10 --codec yuv420 --listen &` can provide a v4l2 loopback if configured) or use the legacy stack if your OS provides it.
- Storage: Images can fill the SD card. The app enforces `SC_MAX_SAVED_IMAGES`; adjust to your capacity.
- Service: To run on boot, wrap `python3 /path/to/main.py` in a `systemd` service.

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
