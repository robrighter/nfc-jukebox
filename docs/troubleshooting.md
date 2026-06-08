# Troubleshooting

## Service and Logs

```bash
# Service status
sudo systemctl status nfc-jukebox.service

# Live log tail
sudo journalctl -u nfc-jukebox.service -f

# Logs since last hour
sudo journalctl -u nfc-jukebox.service --since "1 hour ago"
```

Run the health check:

```bash
sudo ./scripts/healthcheck.sh
```

---

## Alexa / Amazon Issues

### "Alexa client is not connected"

- Check that `AMAZON_EMAIL` and `AMAZON_PASSWORD` are correct in `.env`.
- Run the device discovery script to trigger fresh login:
  ```bash
  cd /opt/nfc-jukebox
  .venv/bin/python scripts/list_alexa_devices.py
  ```
- If login fails, delete the stored login data and retry:
  ```bash
  rm /opt/nfc-jukebox/data/.alexa-login-data.json
  .venv/bin/python scripts/list_alexa_devices.py
  ```

### "Target device not found"

- The `ALEXA_DEVICE_NAME` in `.env` must match exactly what appears in the Alexa app.
- Run `list_alexa_devices.py` and copy the exact name shown.
- Device names are case-insensitive but must otherwise match.

### Alexa plays wrong album / generic search

- The command template determines what Alexa hears.
- Edit the template in the **Settings** page or in `.env`.
- Examples that work well: `play the album {album}`, `play {album} on Spotify`
- Try the **Send Test Command** button in Settings.

### Login stops working after a while

- Amazon sessions expire. Delete stored login data and re-authenticate:
  ```bash
  rm /opt/nfc-jukebox/data/.alexa-login-data.json
  sudo systemctl restart nfc-jukebox.service
  ```
  Check logs for the OTP prompt, or run `list_alexa_devices.py` interactively.

---

## NFC Reader Issues

### Reader not detected / no tags being read

1. Check SPI is enabled:
   ```bash
   ls /dev/spidev*
   ```
   If nothing appears: `sudo raspi-config → Interface Options → SPI → Enable`, then reboot.

2. Check wiring against [hardware-wiring.md](hardware-wiring.md). Common mistakes:
   - 5V connected instead of 3.3V (damages the module)
   - MISO/MOSI swapped
   - Loose jumper wire on RST pin

3. Check the service log for `MFRC522` or `SPI` error messages.

### Tags scanned repeatedly / duplicate commands

- Increase `NFC_RESCAN_COOLDOWN_SECONDS` in `.env` (default: 5).
- Remove the tag from the reader after scanning — the reader sees it every poll cycle while present.

### NFC write times out

- Hold the tag flat and still on the reader center.
- Try a different tag (some are not writable).
- Check that no other write job is in progress (the web UI will say).
- Increase write timeout by modifying `timeout_seconds` in `write_tag_text` if needed.

---

## Web UI Issues

### "http://nfc-jukebox.local:8080" not reachable

1. Confirm the service is running: `sudo systemctl status nfc-jukebox.service`
2. Check the port: `ss -tlnp | grep 8080`
3. Try the IP address instead: `http://192.168.1.xxx:8080`
4. mDNS (`*.local`) requires Avahi on the Pi:
   ```bash
   sudo apt install -y avahi-daemon
   sudo systemctl enable avahi-daemon
   sudo systemctl start avahi-daemon
   ```
5. On Windows, mDNS requires Bonjour (installed with iTunes or Apple devices).

### Web UI shows "NFC: stub mode"

The app is running but `mfrc522` / `RPi.GPIO` aren't available (dev machine, not Pi). This is expected when developing off-device.

---

## Raspberry Pi System Issues

### Pi won't boot

- Re-flash the SD card using Raspberry Pi Imager.
- Try a different power supply (must be 5V/3A).
- Try a different SD card.

### High SD card wear

- Use an endurance-rated SD card (Samsung Endurance Pro, SanDisk High Endurance).
- Or use a USB SSD for the OS drive.
