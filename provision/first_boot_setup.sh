#!/usr/bin/env bash
# First-boot setup for NFC Jukebox on a fresh Raspberry Pi.
# This script calls the main installer and prints next steps.
#
# Usage (from the repo root):
#   sudo ./provision/first_boot_setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "${SCRIPT_DIR}")"

echo "==> NFC Jukebox first-boot setup"
echo ""

# Run main installer
bash "${REPO_DIR}/scripts/install_pi.sh"

echo ""
echo "==> First-boot setup complete."
echo ""
echo "IMPORTANT: Before the app can control Alexa, you must:"
echo ""
echo "  1. Edit /opt/nfc-jukebox/.env and fill in:"
echo "       AMAZON_EMAIL"
echo "       AMAZON_PASSWORD"
echo "       ALEXA_DEVICE_NAME   (exact name from the Alexa app)"
echo ""
echo "  2. Run the Alexa device discovery / first login:"
echo "       cd /opt/nfc-jukebox"
echo "       .venv/bin/python scripts/list_alexa_devices.py"
echo "     Enter your Amazon OTP when prompted."
echo "     Note the exact device name and set it in .env."
echo ""
echo "  3. Restart the service:"
echo "       sudo systemctl restart nfc-jukebox.service"
echo ""
echo "  4. Open the web UI from another device on the same network:"
echo "       http://nfc-jukebox.local:8080"
echo ""
