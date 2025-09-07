#!/usr/bin/env bash
set -euo pipefail

# Raspberry Pi Security Cam environment setup
# - Installs system packages
# - Configures systemd service
# - Creates data directory with proper ownership
# - Optionally opens firewall (UFW)
#
# Usage (run as root):
#   sudo bash scripts/setup_raspi_env.sh \
#     --user pi \
#     --project-dir /home/pi/raspi-security-cam \
#     --port 8000 \
#     --active-windows "22:00-06:00" \
#     --allow-ufw any
#
# Flags:
#   --user USER                 System user that runs the service (default: pi)
#   --project-dir DIR           Repo path containing main.py (default: PWD)
#   --save-dir DIR              Capture directory (default: PROJECT_DIR/data/captures)
#   --port PORT                 HTTP port (default: 8000)
#   --active-windows SPEC       Schedule windows, e.g. "22:00-06:00,12:30-13:30" (default: empty)
#   --allow-ufw CIDR|any|skip   UFW rule to allow access (default: skip)
#   --no-picam2                 Skip installation of python3-picamera2
#

USER_NAME="pi"
PROJECT_DIR="$(pwd)"
PORT=8000
ACTIVE_WINDOWS=""
ALLOW_UFW="skip"
INSTALL_PICAM2=1
SAVE_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) USER_NAME="$2"; shift 2;;
    --project-dir) PROJECT_DIR="$2"; shift 2;;
    --save-dir) SAVE_DIR="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --active-windows) ACTIVE_WINDOWS="$2"; shift 2;;
    --allow-ufw) ALLOW_UFW="$2"; shift 2;;
    --no-picam2) INSTALL_PICAM2=0; shift 1;;
    -h|--help)
      sed -n '1,80p' "$0" | sed -e 's/^# \{0,1\}//'
      exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

if [[ -z "$SAVE_DIR" ]]; then
  SAVE_DIR="$PROJECT_DIR/data/captures"
fi

echo "==> Config summary"
echo "User:           $USER_NAME"
echo "Project dir:    $PROJECT_DIR"
echo "Save dir:       $SAVE_DIR"
echo "Port:           $PORT"
echo "Active windows: ${ACTIVE_WINDOWS:-<always armed>}"
echo "UFW allow:      $ALLOW_UFW"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (use sudo)." >&2
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/main.py" ]]; then
  echo "main.py not found in PROJECT_DIR ($PROJECT_DIR). Adjust --project-dir." >&2
  exit 1
fi

echo "==> Installing system packages"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3-opencv python3-flask python3-numpy \
  ufw

if [[ "$INSTALL_PICAM2" == "1" ]]; then
  # Picamera2 may be unavailable on some releases; ignore failure
  if ! DEBIAN_FRONTEND=noninteractive apt-get install -y python3-picamera2; then
    echo "(warn) python3-picamera2 not available; will use OpenCV V4L2 if possible" >&2
  fi
fi

echo "==> Creating capture directory and setting ownership"
mkdir -p "$SAVE_DIR"
chown -R "$USER_NAME":"$USER_NAME" "$PROJECT_DIR"
# If SAVE_DIR is outside the project directory, ensure ownership as well
if [[ ! "$SAVE_DIR" =~ ^$PROJECT_DIR(/|$) ]]; then
  chown -R "$USER_NAME":"$USER_NAME" "$SAVE_DIR" || true
fi

echo "==> Installing systemd unit"
UNIT_SRC="$PROJECT_DIR/packaging/systemd/raspi-security-cam.service"
UNIT_DST="/etc/systemd/system/raspi-security-cam.service"
if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Missing unit template at $UNIT_SRC" >&2
  exit 1
fi
cp "$UNIT_SRC" "$UNIT_DST"
sed -i -E \
  -e "s|^User=.*$|User=$USER_NAME|" \
  -e "s|^WorkingDirectory=.*$|WorkingDirectory=$PROJECT_DIR|" \
  "$UNIT_DST"

echo "==> Installing environment file at /etc/default/raspi-security-cam"
ENV_DST="/etc/default/raspi-security-cam"
cp "$PROJECT_DIR/packaging/systemd/raspi-security-cam.env.example" "$ENV_DST"
# Escape sed replacement special chars (&) in paths/values
ESC_SAVE_DIR=${SAVE_DIR//&/\\&}
ESC_PORT=${PORT//&/\\&}
sed -i -E \
  -e "s|^SC_PORT=.*$|SC_PORT=${ESC_PORT}|" \
  -e "s|^SC_SAVE_DIR=.*$|SC_SAVE_DIR=${ESC_SAVE_DIR}|" \
  "$ENV_DST"

# ACTIVE_WINDOWS may contain special chars; append or replace more carefully
if grep -q "^SC_ACTIVE_WINDOWS=" "$ENV_DST"; then
  sed -i -E "s|^SC_ACTIVE_WINDOWS=.*$|SC_ACTIVE_WINDOWS=${ACTIVE_WINDOWS}|" "$ENV_DST"
else
  echo "SC_ACTIVE_WINDOWS=${ACTIVE_WINDOWS}" >> "$ENV_DST"
fi

echo "==> Enabling and starting service"
systemctl daemon-reload
systemctl enable raspi-security-cam
systemctl restart raspi-security-cam || systemctl start raspi-security-cam

echo "==> Configuring UFW (if requested)"
if [[ "$ALLOW_UFW" != "skip" ]]; then
  if ! command -v ufw >/dev/null 2>&1; then
    echo "(warn) ufw not installed; skipping firewall rules" >&2
  else
    ufw --force enable || true
    if [[ "$ALLOW_UFW" == "any" ]]; then
      ufw allow "$PORT"/tcp || true
    else
      ufw allow from "$ALLOW_UFW" to any port "$PORT" proto tcp || true
    fi
  fi
fi

echo "==> Ensuring service user has camera access"
# Picamera2/libcamera requires membership in the 'video' group
if ! id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx "video"; then
  usermod -aG video "$USER_NAME" || true
  echo "(info) Added $USER_NAME to 'video' group for camera access" >&2
fi

echo "(info) Not toggling legacy camera via raspi-config to avoid conflicts with Picamera2/libcamera."
echo "       Use 'sudo raspi-config' to verify camera enablement if needed."

echo "==> Done"
echo "Service status: systemctl status raspi-security-cam --no-pager"
echo "Open dashboard at: http://<pi-ip>:${PORT}/"
