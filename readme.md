# Raspberry Pi Security Camera – Step‑by‑Step Setup (Fresh Install)

This guide walks you from a fresh Raspberry Pi OS install to a working, auto‑starting security camera app with human detection and a simple web dashboard.

## 1) Hardware + OS
- Raspberry Pi 3B (works on others, but defaults tuned for 3B)
- Raspberry Pi Camera Module (v1/ov5647, v2/imx219, HQ/imx477, or v3/imx708)
- Raspberry Pi OS (Bookworm recommended)
- Network connectivity (LAN)

## 2) Update OS
```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

## 3) Enable the camera (libcamera stack)
- Use `raspi-config` to ensure interfaces are enabled:
```bash
sudo raspi-config
# Interface Options → I2C → Enable (recommended)
# Legacy Camera should remain DISABLED on Bookworm
```
- If your camera isn’t auto‑detected, you can force the overlay later (see Troubleshooting).

## 4) Install required packages
Use system packages for speed and compatibility on the Pi:
```bash
sudo apt update
sudo apt install -y python3-opencv python3-flask python3-numpy python3-picamera2 ufw
# Optional tools for camera diagnostics
sudo apt install -y rpicam-apps v4l-utils
```

## 5) Get the app into your Pi
If you already have the repo on the Pi, skip cloning.
```bash
cd ~
# Example path; adjust if using a different directory
mkdir -p ~/work && cd ~/work
# If using git (replace URL with your repo origin):
# git clone <your-repo-url> utl-secam
# cd utl-secam
# If you copied the files already, just cd into that directory instead.
```

## 6) One‑shot setup (recommended)
The script installs packages (idempotent), sets up systemd, writes env defaults, optionally opens the firewall, and starts the service.
```bash
cd /path/to/utl-secam
sudo bash scripts/setup_raspi_env.sh \
  --user $USER \
  --project-dir $(pwd) \
  --port 8000 \
  --active-windows "22:00-06:00" \
  --allow-ufw 192.168.10.0/24   # your LAN CIDR, or use 'any' or 'skip'
```
Notes:
- Use your real project directory and LAN subnet.
- If you see chown errors for `pi:pi`, pass `--user <your-username>`.
- The service name is `raspi-security-cam`.

## 7) Verify service + dashboard
```bash
# Check it’s running and listening
sudo systemctl status raspi-security-cam --no-pager
sudo ss -lntp | grep :8000 || true
# Open in a browser from another device on the same LAN
# http://<pi-ip>:8000/
```
Endpoints:
- Latest frame: `http://<pi-ip>:8000/latest.jpg`
- MJPEG stream: `http://<pi-ip>:8000/stream.mjpg`
- JSON state: `http://<pi-ip>:8000/api/state`

## 8) Configure behavior
Edit the environment file used by the service:
```bash
sudoedit /etc/default/raspi-security-cam
# Common settings to review:
# SC_HOST=0.0.0.0
# SC_PORT=8000
# SC_CAMERA_BACKEND=picamera2   # or v4l2 or auto
# SC_FRAME_WIDTH=640
# SC_FRAME_HEIGHT=480
# SC_CAPTURE_FPS=5
# SC_DETECT_EVERY_N_FRAMES=2
# SC_SAVE_DIR=/path/to/data/captures
# SC_ACTIVE_WINDOWS="22:00-06:00"  # schedule (empty = always armed)
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
```bash
sudo systemctl restart raspi-security-cam
```

## 9) Firewall (UFW)
Allow the dashboard port on your LAN (adjust subnet):
```bash
sudo ufw allow from 192.168.10.0/24 to any port 8000 proto tcp
sudo ufw status
```
Alternative: keep it closed and tunnel over SSH:
```bash
ssh -L 8000:localhost:8000 pi@<pi-ip>
# then open http://localhost:8000
```

## 10) Camera diagnostics
If frames stay at 0, check the camera outside the app:
```bash
# Stop the service to free the camera
sudo systemctl stop raspi-security-cam
# Test with libcamera/rpicam
rpicam-hello -n -t 2000
# List video devices
v4l2-ctl --list-devices
# Common dmesg probes
dmesg | grep -i -E 'imx|ov|unicam|camera'
```
If “no cameras available”:
- Power off, reseat the ribbon cable (CSI connector, correct orientation), power on.
- Force the camera overlay if you know the model: edit `/boot/firmware/config.txt` and add one of:
  - `dtoverlay=ov5647` (v1)
  - `dtoverlay=imx219` (v2)
  - `dtoverlay=imx477` (HQ)
  - `dtoverlay=imx708` (v3)
- Reboot, test again. When working, start the service:
```bash
sudo systemctl start raspi-security-cam
```

## 11) Service management
```bash
# Start/stop/restart
sudo systemctl start raspi-security-cam
sudo systemctl stop raspi-security-cam
sudo systemctl restart raspi-security-cam
# Logs
sudo journalctl -u raspi-security-cam -f
```

## 12) Where files live
- Code: project directory you cloned/copied (e.g., `/home/<user>/work/utl-secam`)
- Captures: `data/captures/` (configurable via `SC_SAVE_DIR`)
- Systemd unit: `/etc/systemd/system/raspi-security-cam.service`
- Service env: `/etc/default/raspi-security-cam`

## 13) Uninstall / disable
```bash
sudo systemctl disable --now raspi-security-cam
sudo rm /etc/systemd/system/raspi-security-cam.service
sudo rm /etc/default/raspi-security-cam
sudo systemctl daemon-reload
```
(Optionally remove the project folder and captures directory.)

## 14) Security notes
- The dashboard has no authentication; do not expose it to the internet.
- Restrict UFW rules to your LAN or use SSH/VPN.
- Consider running behind a reverse proxy on port 80 with basic auth if needed.

## 15) Performance tips (Pi 3B)
- Use 640x480 at 5 FPS: good balance of CPU vs clarity.
- `SC_DETECT_EVERY_N_FRAMES=2` reduces CPU while keeping detection responsive.
- Adaptive sensitivity is enabled by default to auto‑tune detection in poor lighting.

---
If you get stuck, check the service logs and the `/api/state` endpoint, then adjust camera backend (`SC_CAMERA_BACKEND`) and capture size/FPS to suit your device.

