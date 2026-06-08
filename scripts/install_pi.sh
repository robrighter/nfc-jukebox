#!/usr/bin/env bash
# Install NFC Jukebox on a Raspberry Pi running Raspberry Pi OS (Debian-based).
# Run as root: sudo ./scripts/install_pi.sh

set -e

INSTALL_DIR="/opt/nfc-jukebox"
DATA_DIR="${INSTALL_DIR}/data"
SERVICE_FILE="provision/nfc-jukebox.service"
SYSTEMD_DIR="/etc/systemd/system"

# ---- checks ----

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Error: this script must be run as root (use sudo)." >&2
  exit 1
fi

if ! command -v apt-get &>/dev/null; then
  echo "Error: apt-get not found. This script requires a Debian-based system." >&2
  exit 1
fi

echo "==> NFC Jukebox installer"
echo "    Install directory: ${INSTALL_DIR}"
echo ""

# ---- system packages ----

echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip git i2c-tools python3-dev build-essential

# ---- enable SPI ----

if command -v raspi-config &>/dev/null; then
  echo "==> Enabling SPI..."
  raspi-config nonint do_spi 0 || echo "    Warning: could not enable SPI via raspi-config"
else
  echo "    raspi-config not found — skipping SPI enable. Enable SPI manually if needed."
fi

# ---- create directories ----

echo "==> Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${DATA_DIR}"

# ---- copy repo ----

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "${SCRIPT_DIR}")"

echo "==> Copying repo from ${REPO_DIR} to ${INSTALL_DIR}..."
rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
      --exclude='*.pyc' --exclude='data/' \
      "${REPO_DIR}/" "${INSTALL_DIR}/"

# ---- virtual environment ----

echo "==> Creating Python virtual environment..."
python3 -m venv "${INSTALL_DIR}/.venv"

echo "==> Installing Python dependencies..."
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip -q
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

# ---- .env file ----

if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  echo "==> Creating .env from template..."
  cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
  echo "    Edit ${INSTALL_DIR}/.env before starting the service."
else
  echo "    ${INSTALL_DIR}/.env already exists — not overwriting."
fi

# ---- systemd service ----

if [[ -f "${INSTALL_DIR}/${SERVICE_FILE}" ]]; then
  echo "==> Installing systemd service..."
  cp "${INSTALL_DIR}/${SERVICE_FILE}" "${SYSTEMD_DIR}/nfc-jukebox.service"
  systemctl daemon-reload
  systemctl enable nfc-jukebox.service
  systemctl restart nfc-jukebox.service
  echo "    Service installed and started."
else
  echo "    Warning: ${SERVICE_FILE} not found — skipping service install."
fi

# ---- done ----

echo ""
echo "==> Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Edit ${INSTALL_DIR}/.env and set your Amazon credentials and device name."
echo "  2. Run the Alexa device discovery script (first login):"
echo "       cd ${INSTALL_DIR} && .venv/bin/python scripts/list_alexa_devices.py"
echo "  3. Check service status:"
echo "       sudo systemctl status nfc-jukebox.service"
echo "  4. View logs:"
echo "       sudo journalctl -u nfc-jukebox.service -f"
echo "  5. Open the web UI:"
echo "       http://nfc-jukebox.local:8080"
echo ""
