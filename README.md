# NFC Jukebox

An NFC tag-based Alexa album jukebox for Raspberry Pi 4.

Place an NFC card on the reader → Alexa plays the album.

## How it works

1. Each NFC tag stores an album/search string (e.g. `Abbey Road by The Beatles`).
2. Scanning a tag sends a voice command to the configured Amazon Echo device.
3. The command is built from a configurable template: `play the album {album}`.
4. Alexa plays the album using whatever music provider it's configured to use.

A local web interface lets you manage albums, write NFC tags, and adjust settings — all from a phone on the same network.

---

## Hardware

- Raspberry Pi 4
- MicroSD card (16 GB+) or USB SSD
- MFRC522 RFID/NFC reader (13.56 MHz)
- NFC cards or key fobs (MIFARE Classic 1K)
- Optional: status LED + resistor
- Amazon Echo / Alexa device on the same network

See [docs/hardware-wiring.md](docs/hardware-wiring.md) for wiring details.

---

## Quick Start (development / non-Pi)

```bash
cp .env.example .env
# Edit .env with your Amazon credentials and device name

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py
# or: uvicorn nfc_jukebox.app:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080

On a non-Pi machine, the app runs in stub mode (no GPIO/NFC hardware). All web UI features work; scanning/writing just simulates.

---

## Raspberry Pi Appliance Setup

For a full appliance install from scratch:

1. **Flash the OS** — see [docs/make-raspberry-pi-image.md](docs/make-raspberry-pi-image.md)
2. **SSH into the Pi** and clone this repo
3. **Run the installer**:
   ```bash
   sudo ./scripts/install_pi.sh
   ```
4. **Configure** `/opt/nfc-jukebox/.env` (set `ALEXA_DEVICE_NAME`; leave Amazon credentials blank)
5. **Connect Amazon** in the web UI at `http://nfc-jukebox.local:8080/setup`
6. **Open the web UI**: http://nfc-jukebox.local:8080

Full guide: [docs/raspberry-pi-4-appliance-setup.md](docs/raspberry-pi-4-appliance-setup.md)

> **Requires Raspberry Pi OS Trixie** (Python 3.12+). The Alexa library
> `aioamazondevices` does not run on Bookworm's Python 3.11.

---

## Connect Amazon (passkey-friendly, no password stored)

The app uses [`aioamazondevices`](https://github.com/chemelli74/aioamazondevices) to send text commands to Alexa, authenticated with Amazon's OAuth device flow.

**You never put your Amazon password on the Pi.** Instead:

1. Open `http://nfc-jukebox.local:8080/setup`
2. Click **Start Amazon Sign-In** → open the generated link
3. Sign in to Amazon **in your own browser** — your passkey works here
4. Amazon lands you on a near-blank `…/ap/maplanding?…` page. Copy the full address-bar URL
5. Paste it back into the setup page → **Finish Connecting**

The Pi exchanges the one-time authorization code for a **revocable device token** and stores only that. Revoke anytime from Amazon → *Manage Your Content and Devices → Devices*.

Then set `ALEXA_DEVICE_NAME` in `.env` to your Echo's exact name (the
`scripts/list_alexa_devices.py` helper prints available names once connected).

> **Note:** This uses an unofficial Amazon interface. If commands stop working, re-run the `/setup` flow to refresh the token.

---

## Web UI

```
http://nfc-jukebox.local:8080
```

Or by IP:

```
http://<raspberry-pi-ip>:8080
```

| Page | URL |
|------|-----|
| Dashboard | `/` |
| Albums | `/albums` |
| Add album | `/albums/new` |
| Write NFC tag | `/albums/{id}/write` |
| Settings | `/settings` |
| Connect Amazon | `/setup` |
| System status | `/status` |

---

## Adding Albums and Writing Tags

1. Go to **Albums → Add Album**
2. Enter the album text: `Kind of Blue by Miles Davis`
3. Click **Write Tag** → **Start Writing Tag**
4. Place a blank NFC card on the reader and hold it still
5. The page confirms when writing is complete

Scanning that tag later will send: `play the album Kind of Blue by Miles Davis`

---

## NFC Tag Format

Tags contain plain text only — the album/search string exactly as you want it sent to Alexa.

Examples:
```
Abbey Road by The Beatles
Kind of Blue by Miles Davis
Rumours by Fleetwood Mac
Led Zeppelin IV
```

---

## Alexa Command Template

The default template is `play the album {album}`. Edit it in the **Settings** page.

More examples:

```
play the album {album}
play {album} on Spotify
play {album} on Amazon Music
shuffle {album}
play the playlist {album}
```

`{album}` is replaced with the text read from the NFC tag.

---

## Helper Scripts

```bash
# List available Alexa devices
python scripts/list_alexa_devices.py

# Send a test command
python scripts/send_test_command.py "play the album Abbey Road by The Beatles"

# Initialise the database manually
python scripts/init_db.py
```

---

## Service Logs

```bash
sudo systemctl status nfc-jukebox.service
sudo journalctl -u nfc-jukebox.service -f
```

---

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md) for common issues:
- Alexa not connected
- Device not found
- NFC reader not detected
- SPI not enabled
- Web UI not reachable

---

## Security Notes

- The web UI is intended for **local network use only**. Do not expose port 8080 to the internet.
- Set `WEB_UI_PASSWORD` in `.env` for basic password protection if desired.
- Never commit `.env` or `data/.alexa-login-data.json` to version control.
- Keep your Amazon credentials in `.env` only — they are excluded from git by `.gitignore`.
