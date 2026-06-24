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

# Complete Setup Guide (start to finish)

Follow these in order. The whole thing takes ~30 minutes, most of it unattended.

## What you need

**Hardware**

- Raspberry Pi 4 (any RAM size) + official USB-C power supply (5V/3A)
- MicroSD card, 16 GB or larger (an endurance-rated card is best for 24/7 use)
- An SD card reader for your laptop
- MFRC522 RFID/NFC reader module (13.56 MHz)
- 7 female-to-female jumper wires (to wire the reader to the Pi)
- NFC cards or key fobs — **MIFARE Classic 1K** or compatible (13.56 MHz)
- *Optional:* a 5 mm LED + a 220–470 Ω resistor for scan feedback
- An Amazon Echo / Alexa device, already set up and on your Wi-Fi

**Software to download (on your laptop)**

- **Raspberry Pi Imager** — https://www.raspberrypi.com/software/
  (Windows/macOS/Linux; this writes the SD card)
- **Git for Windows** (only if you use the scripted flasher) — https://git-scm.com/download/win
  (provides `openssl`, used to hash your Pi password)
- Windows 10/11 already includes the `ssh`, `scp`, and `tar` tools the finish
  script needs.

> **Important — OS version:** this project needs **Raspberry Pi OS Trixie**
> (Python 3.12+). The Alexa library does not run on the older Bookworm release
> (Python 3.11). The steps below select the right image.

## Step 0 — Wire the MFRC522 reader to the Pi

Do this with the Pi **powered off**. Connect 7 jumper wires exactly as below.
Pin numbers are physical board pins (see the diagram in
[docs/hardware-wiring.md](docs/hardware-wiring.md)).

| MFRC522 pin | → Raspberry Pi pin | Pi signal |
|-------------|--------------------|-----------|
| SDA / SS    | Pin 24             | GPIO 8 (CE0) |
| SCK         | Pin 23             | GPIO 11 (SCLK) |
| MOSI        | Pin 19             | GPIO 10 (MOSI) |
| MISO        | Pin 21             | GPIO 9 (MISO) |
| GND         | Pin 6              | Ground |
| RST         | Pin 22             | GPIO 25 |
| 3.3V        | Pin 1              | 3.3V power |
| IRQ         | *(leave unconnected)* | — |

> ⚠️ Use the **3.3V** pin (pin 1), **not** 5V — 5V can damage the MFRC522.

*Optional LED:* long leg (+) → a 220–470 Ω resistor → **Pin 18** (GPIO 24);
short leg (−) → **Pin 20** (GND).

## Step 1 — Flash the SD card

Insert the SD card into your laptop, then pick **one** option.

### Option A — Raspberry Pi Imager GUI (recommended, most reliable)

1. Install and open **Raspberry Pi Imager**.
2. **Choose Device:** Raspberry Pi 4.
3. **Choose OS:** *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (64-bit)**.
   Make sure it's the **Trixie** release (Python 3.12+).
4. **Choose Storage:** your SD card.
5. Click **Next → Edit Settings** and set:
   - **Hostname:** `nfc-jukebox`
   - **Username:** `pi` and a password you'll remember
   - **Wi-Fi:** your SSID + password + your country (skip if using Ethernet)
   - **Locale:** your time zone
   - **Services tab → Enable SSH** → *Use password authentication*
6. **Save → Write.** Wait for it to finish and verify, then eject.

### Option B — Scripted flasher (advanced, Windows)

One command writes the image *and* pre-configures headless boot (hostname, your
user, SSH key, Wi-Fi). Open an **Administrator** PowerShell in the repo folder:

```powershell
.\provision\flash_sd_card.ps1
```

It will: detect your SD card (and make you confirm it by number, then type
`YES`), write the latest Raspberry Pi OS Lite 64-bit, and drop a `custom.toml`
onto the card for first-boot setup. It uses an SSH key (auto-generated if you
don't have one) so the finish script can log in without a password.

> This performs a raw disk write and depends on your exact machine. If the disk
> list looks at all wrong, abort and use Option A.

## Step 2 — Boot the Pi and find its IP address

1. Eject the SD card and insert it into the **powered-off** Pi.
2. Connect Ethernet now if you're not using Wi-Fi.
3. Power on the Pi. **Wait ~90 seconds** for the first boot.
4. Find the Pi's IP address — any of:
   - Try the hostname first: it's often reachable as `nfc-jukebox.local`
   - Open your **router's** admin page → look for the device named `nfc-jukebox`
   - Or plug in a monitor briefly — the IP prints above the login prompt

Note the IP, e.g. `192.168.1.42`.

## Step 3 — Finish setup from your laptop

This copies the app to the Pi, installs everything (system packages, SPI,
service), and starts it — all over SSH. From the repo folder in PowerShell:

```powershell
.\provision\finish_setup.ps1 -PiHost 192.168.1.42 -User pi -DeviceName "Kitchen Echo"
```

- Replace the IP with your Pi's.
- `-DeviceName` is your Echo's **exact** name from the Alexa app (optional — you
  can set it later in Settings).
- If you flashed with **Option A** (password SSH), you'll be prompted for the
  Pi password a couple of times. With **Option B** (key auth) it's hands-off.

When it finishes it prints your web UI URL.

## Step 4 — Connect your Amazon account (passkey-friendly)

Open the setup page in your browser:

```
http://nfc-jukebox.local:8080/setup     (or http://<pi-ip>:8080/setup)
```

1. Click **Start Amazon Sign-In**, then open the generated link.
2. Sign in to Amazon **in your own browser** — your **passkey works here**.
3. Amazon sends you to a near-blank `…/ap/maplanding?…` page. Copy the **full
   address-bar URL**.
4. Paste it back into the setup page → **Finish Connecting**.

Your password/passkey never touch the Pi — only a **revocable device token** is
stored. Revoke it anytime at Amazon → *Manage Your Content and Devices →
Devices*.

## Step 5 — Add an album and write your first tag

1. Open `http://nfc-jukebox.local:8080`, go to **Albums → + Add Album**.
2. Enter e.g. `Abbey Road by The Beatles` and save.
3. Click **Write Tag → Start Writing Tag**, place a blank NFC card on the
   reader, and hold still until it says **Done**.
4. Tap that card on the reader anytime — Alexa plays the album. 🎵

*(Optional advanced verification: before relying on the web flow you can run
`scripts/verify_amazon_setup.py` on the Pi to validate the Amazon integration —
see [docs/troubleshooting.md](docs/troubleshooting.md).)*

---

## Hardware reference

- Raspberry Pi 4
- MicroSD card (16 GB+) or USB SSD
- MFRC522 RFID/NFC reader (13.56 MHz)
- NFC cards or key fobs (MIFARE Classic 1K)
- Optional: status LED + resistor
- Amazon Echo / Alexa device on the same network

Full wiring diagram and pinout: [docs/hardware-wiring.md](docs/hardware-wiring.md).

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
