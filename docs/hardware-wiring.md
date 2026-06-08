# Hardware Wiring

## MFRC522 NFC Reader

The MFRC522 connects to the Raspberry Pi 4 via SPI.

| MFRC522 Pin | Raspberry Pi GPIO | Physical Pin | Notes         |
|-------------|-------------------|--------------|---------------|
| SDA / SS    | GPIO 8 (CE0)      | Pin 24       | SPI chip select |
| SCK         | GPIO 11 (SCLK)    | Pin 23       | SPI clock     |
| MOSI        | GPIO 10 (MOSI)    | Pin 19       | SPI data out  |
| MISO        | GPIO 9 (MISO)     | Pin 21       | SPI data in   |
| IRQ         | —                 | —            | Not connected |
| GND         | GND               | Pin 6        |               |
| RST         | GPIO 25           | Pin 22       | Reset         |
| 3.3V        | 3.3V              | Pin 1        | Power         |

> **Warning:** Use the 3.3V pin, not 5V. The MFRC522 is not 5V tolerant.

### Enable SPI

SPI must be enabled before the reader will work:

```bash
sudo raspi-config
# Interface Options → SPI → Enable
```

Or non-interactively:

```bash
sudo raspi-config nonint do_spi 0
```

Reboot after enabling SPI.

---

## Status LED (optional)

A single LED provides scan feedback.

| Component       | Connection                          |
|-----------------|-------------------------------------|
| LED anode (+)   | GPIO 24 (Pin 18) through a resistor |
| LED cathode (−) | GND (Pin 20)                        |

Use a 220–470 Ω resistor in series with the LED to limit current.

LED behavior:
- **On** while sending a command to Alexa
- **Off** after success
- **Blinks 3×** on error
- **On (steady)** while writing an NFC tag

To use a different GPIO pin, set `LED_PIN` in `.env`.

---

## Raspberry Pi 4 GPIO Pinout Reference

```
        3V3  (1) (2)  5V
      GPIO2  (3) (4)  5V
      GPIO3  (5) (6)  GND
      GPIO4  (7) (8)  GPIO14
        GND  (9) (10) GPIO15
     GPIO17 (11) (12) GPIO18
     GPIO27 (13) (14) GND
     GPIO22 (15) (16) GPIO23
        3V3 (17) (18) GPIO24  <-- LED
     GPIO10 (19) (20) GND
      GPIO9 (21) (22) GPIO25  <-- MFRC522 RST
     GPIO11 (23) (24) GPIO8   <-- MFRC522 SDA/SS
        GND (25) (26) GPIO7
      GPIO0 (27) (28) GPIO1
      GPIO5 (29) (30) GND
      GPIO6 (31) (32) GPIO12
     GPIO13 (33) (34) GND
     GPIO19 (35) (36) GPIO16
     GPIO26 (37) (38) GPIO20
        GND (39) (40) GPIO21
```
