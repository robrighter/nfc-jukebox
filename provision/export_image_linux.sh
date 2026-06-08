#!/usr/bin/env bash
# Export a Raspberry Pi SD card / SSD to an image file.
#
# Usage:
#   sudo ./provision/export_image_linux.sh /dev/sdX ./out/nfc-jukebox-pi4.img
#   sudo ./provision/export_image_linux.sh /dev/sdX ./out/nfc-jukebox-pi4.img.xz  # compressed
#
# WARNING: This reads raw block device data. Make sure you select the right device.
# The Pi should be powered off and the storage removed before imaging.

set -e

DEVICE="${1:-}"
OUTPUT="${2:-}"
FORCE="${3:-}"

if [[ -z "$DEVICE" || -z "$OUTPUT" ]]; then
  echo "Usage: sudo $0 <block-device> <output-file> [--force]"
  echo "  Example: sudo $0 /dev/sdb ./out/nfc-jukebox-pi4.img"
  echo "  Example: sudo $0 /dev/sdb ./out/nfc-jukebox-pi4.img.xz"
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Error: this script must be run as root (use sudo)." >&2
  exit 1
fi

if [[ ! -b "$DEVICE" ]]; then
  echo "Error: $DEVICE is not a block device." >&2
  exit 1
fi

# Safety: refuse /dev/sda without --force
if [[ "$DEVICE" == "/dev/sda" && "$FORCE" != "--force" ]]; then
  echo "Error: refusing to image /dev/sda (likely your main disk)." >&2
  echo "If you really mean it, run with --force as the third argument." >&2
  exit 1
fi

echo "==> Device info:"
lsblk "$DEVICE"
echo ""
echo "Source device : $DEVICE"
echo "Output file   : $OUTPUT"
echo ""
read -r -p "Are you sure you want to image $DEVICE? Type YES to continue: " CONFIRM
if [[ "$CONFIRM" != "YES" ]]; then
  echo "Aborted."
  exit 0
fi

mkdir -p "$(dirname "$OUTPUT")"

if [[ "$OUTPUT" == *.xz ]]; then
  echo "==> Reading $DEVICE and compressing to $OUTPUT ..."
  dd if="$DEVICE" bs=4M status=progress | xz -T0 -v > "$OUTPUT"
else
  echo "==> Reading $DEVICE to $OUTPUT ..."
  dd if="$DEVICE" of="$OUTPUT" bs=4M status=progress conv=fsync
fi

echo ""
echo "==> Done. Image saved to: $OUTPUT"
echo "    Flash to another card with:"
if [[ "$OUTPUT" == *.xz ]]; then
  echo "      xzcat $OUTPUT | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync"
else
  echo "      sudo dd if=$OUTPUT of=/dev/sdX bs=4M status=progress conv=fsync"
fi
