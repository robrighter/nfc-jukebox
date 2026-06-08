# Raspberry Pi 4 Appliance Setup

## Hardware Requirements

- Raspberry Pi 4 (any RAM variant)
- MicroSD card (16 GB+, endurance-rated) or USB SSD
- MFRC522 RFID/NFC reader module
- NFC cards or tags (MIFARE Classic 1K or compatible)
- Optional: status LED + 220–470 Ω resistor
- Power supply: official Raspberry Pi USB-C power adapter (5V/3A)

See [hardware-wiring.md](hardware-wiring.md) for wiring details.

---

## Installation

See [make-raspberry-pi-image.md](make-raspberry-pi-image.md) for how to flash the OS and run the installer.

The installer (`scripts/install_pi.sh`) does everything automatically:
- Installs system packages
- Enables SPI
- Creates `/opt/nfc-jukebox` with a Python virtualenv
- Installs and starts the systemd service

---

## Configuration

All configuration lives in `/opt/nfc-jukebox/.env`.

```bash
sudo nano /opt/nfc-jukebox/.env
```

Key settings:

| Variable | Description |
|---|---|
| `AMAZON_EMAIL` | Your Amazon account email |
| `AMAZON_PASSWORD` | Your Amazon account password |
| `ALEXA_DEVICE_NAME` | Name of your Echo device (must match Alexa app exactly) |
| `ALEXA_COMMAND_TEMPLATE` | Command sent to Alexa (default: `play the album {album}`) |
| `LED_PIN` | GPIO pin for status LED (default: 24) |
| `WEB_PORT` | Web UI port (default: 8080) |
| `WEB_UI_PASSWORD` | Optional password to protect the web UI |

After editing `.env`, restart the service:

```bash
sudo systemctl restart nfc-jukebox.service
```

---

## First Alexa Login

On first run, you must authenticate with Amazon:

```bash
cd /opt/nfc-jukebox
.venv/bin/python scripts/list_alexa_devices.py
```

You will be prompted for your Amazon OTP (two-factor code). After login succeeds, the session is saved to `ALEXA_LOGIN_DATA_FILE` and future starts are automatic.

Note the exact device name printed and set it as `ALEXA_DEVICE_NAME` in `.env`.

---

## Service Management

```bash
# Check status
sudo systemctl status nfc-jukebox.service

# Start / stop / restart
sudo systemctl start nfc-jukebox.service
sudo systemctl stop nfc-jukebox.service
sudo systemctl restart nfc-jukebox.service

# Live logs
sudo journalctl -u nfc-jukebox.service -f

# Recent logs
sudo journalctl -u nfc-jukebox.service --since "1 hour ago"
```

---

## Web Interface

Access from any device on the same network:

```
http://nfc-jukebox.local:8080
```

If mDNS (`nfc-jukebox.local`) doesn't work, use the Pi's IP address:

```
http://192.168.1.xxx:8080
```

Find the IP with:

```bash
hostname -I
```

---

## Adding Albums and Writing NFC Tags

1. Open the web UI and go to **Albums**.
2. Click **+ Add Album** and enter the album/search text (e.g. `Kind of Blue by Miles Davis`).
3. Click **Write Tag** next to the album.
4. Click **Start Writing Tag** and place a blank NFC card on the MFRC522 reader.
5. Hold the card still until the page says **Done**.

The tag now contains that album text. Scanning it will send the configured Alexa command.

---

## NFC Tag Compatibility

The MFRC522 works with:
- MIFARE Classic 1K (most common white cards and key fobs)
- MIFARE Ultralight
- ISO/IEC 14443-A compatible tags

13.56 MHz tags only. The reader does not support 125 kHz EM4100 tags.
