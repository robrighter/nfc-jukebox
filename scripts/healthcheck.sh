#!/usr/bin/env bash
# Health check for the NFC Jukebox service.

set -e

PORT="${WEB_PORT:-8080}"
PASS=0
FAIL=0

check() {
  local label="$1"
  local result="$2"
  if [[ "$result" == "ok" ]]; then
    echo "  [OK]   ${label}"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] ${label}: ${result}"
    FAIL=$((FAIL + 1))
  fi
}

echo "==> NFC Jukebox health check"
echo ""

# systemd service active
if systemctl is-active --quiet nfc-jukebox.service 2>/dev/null; then
  check "systemd service is active" "ok"
else
  check "systemd service is active" "nfc-jukebox.service is not running"
fi

# Port listening
if ss -tlnp 2>/dev/null | grep -q ":${PORT}"; then
  check "Web port ${PORT} is listening" "ok"
elif netstat -tlnp 2>/dev/null | grep -q ":${PORT}"; then
  check "Web port ${PORT} is listening" "ok"
else
  check "Web port ${PORT} is listening" "nothing listening on port ${PORT}"
fi

# /api/status returns 200
if command -v curl &>/dev/null; then
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/api/status" 2>/dev/null || echo "000")
  if [[ "$HTTP_STATUS" == "200" ]]; then
    check "/api/status returns HTTP 200" "ok"
  else
    check "/api/status returns HTTP 200" "got HTTP ${HTTP_STATUS}"
  fi
else
  check "/api/status reachable" "curl not installed — skipping"
fi

# SPI device
if [[ -e /dev/spidev0.0 ]]; then
  check "SPI device /dev/spidev0.0 exists" "ok"
else
  check "SPI device /dev/spidev0.0 exists" "not found — is SPI enabled? (sudo raspi-config)"
fi

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed."
[[ "$FAIL" -eq 0 ]]
