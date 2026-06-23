# Making a Raspberry Pi Image

## Option 1: Manual Install (recommended for first setup)

### 1. Install Raspberry Pi Imager

Download from [raspberrypi.com/software](https://www.raspberrypi.com/software/) for Mac, Windows, or Linux.

### 2. Flash the OS

1. Insert a microSD card (16 GB or larger) or USB SSD.
2. Open Raspberry Pi Imager.
3. **Choose Device**: Raspberry Pi 4
4. **Choose OS**: Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)**
   - **Use the Trixie release** (Python 3.12+). The Alexa library
     `aioamazondevices` requires Python ≥ 3.12 and will not install on the
     older Bookworm release (Python 3.11). Check with `python3 --version`
     after first boot — it should report 3.12 or newer.
5. **Choose Storage**: your microSD / SSD
6. Click **Edit Settings** (gear icon) and configure:
   - **Hostname**: `nfc-jukebox`
   - **Username**: `pi` (or your preferred name)
   - **Password**: set a strong password
   - **Wi-Fi**: enter your network SSID and password (if not using Ethernet)
   - **Locale**: set your time zone and keyboard layout
   - **Enable SSH**: check "Allow public-key authentication only" or "Use password authentication"
7. Click **Save**, then **Write**.

### 3. First Boot

1. Insert the card into the Raspberry Pi 4 and power it on.
2. Wait ~60 seconds for first boot.
3. SSH in from another computer:
   ```bash
   ssh pi@nfc-jukebox.local
   ```
   If mDNS doesn't work, find the IP in your router's DHCP table and use that instead.

### 4. Install NFC Jukebox

```bash
# Clone the repo
git clone https://github.com/robrighter/nfc-jukebox.git
cd nfc-jukebox

# Run the installer (installs dependencies, creates service)
sudo ./scripts/install_pi.sh
```

### 5. Configure

```bash
sudo nano /opt/nfc-jukebox/.env
```

Set at minimum:
- `ALEXA_DEVICE_NAME` (exact name from the Alexa app)

Leave `AMAZON_EMAIL` / `AMAZON_PASSWORD` blank — you'll connect in the browser.

### 6. Connect Amazon (passkey-friendly)

Open the setup page from any device on your network:

```
http://nfc-jukebox.local:8080/setup
```

Click **Start Amazon Sign-In**, open the generated link, sign in to Amazon in
your own browser (passkey works), then copy the resulting `…/ap/maplanding?…`
URL back into the page and click **Finish Connecting**. Only a revocable device
token is stored on the Pi — your password never touches it.

### 7. Restart the Service

```bash
sudo systemctl restart nfc-jukebox.service
```

### 8. Open the Web UI

From another device on the same network:

```
http://nfc-jukebox.local:8080
```

---

## Option 2: Reusable Appliance Image

Once one Pi is fully configured and tested, you can clone it to use on additional Pis.

### Create the image

1. Shut the Pi down cleanly:
   ```bash
   sudo shutdown now
   ```
2. Remove the microSD card / SSD.
3. Insert it into a Linux computer.
4. Use the provided helper script:
   ```bash
   sudo ./provision/export_image_linux.sh /dev/sdX ./out/nfc-jukebox-pi4.img.xz
   ```
   Replace `/dev/sdX` with the actual device (check with `lsblk`).

> **Warning:** double-check the device path. Imaging the wrong device will destroy data.

### Flash to a new card

```bash
xzcat ./out/nfc-jukebox-pi4.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
```

Or use Raspberry Pi Imager → **Use custom image**.

### After flashing a clone

If you run multiple Jukeboxes on the same network, change the hostname on each clone:

```bash
sudo hostnamectl set-hostname nfc-jukebox-2
sudo nano /etc/hosts   # update 127.0.1.1 entry to match new hostname
sudo reboot
```

Also update `.env` if each Pi needs its own Alexa device.

---

## Storage recommendations

- **MicroSD**: Samsung Endurance Pro or SanDisk High Endurance (rated for continuous write)
- **USB SSD**: any USB 3.0 SSD for better durability and speed
