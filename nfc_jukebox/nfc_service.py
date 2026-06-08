"""NFC reader/writer service using MFRC522."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Try importing GPIO and mfrc522; fall back to stubs on non-Pi hardware.
try:
    import RPi.GPIO as GPIO  # type: ignore
    _GPIO_AVAILABLE = True
except ImportError:
    logger.warning("RPi.GPIO not available — running in stub mode (no GPIO/LED)")
    _GPIO_AVAILABLE = False
    GPIO = None  # type: ignore

try:
    from mfrc522 import SimpleMFRC522  # type: ignore
    _MFRC522_AVAILABLE = True
except ImportError:
    logger.warning("mfrc522 not available — NFC reads/writes will be simulated")
    _MFRC522_AVAILABLE = False
    SimpleMFRC522 = None  # type: ignore


def _normalize_text(raw: str) -> str:
    """Strip null bytes, whitespace, collapse internal spaces."""
    text = raw.replace("\x00", "").strip()
    text = re.sub(r" {2,}", " ", text)
    return text


class NfcService:
    def __init__(self, led_pin: int) -> None:
        self._led_pin = led_pin
        self._reader: Optional[object] = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._mode: str = "idle"  # idle | scanning | writing | error
        self._write_cancelled: bool = False

    def setup(self) -> None:
        """Initialise GPIO and MFRC522."""
        if _GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self._led_pin, GPIO.OUT)
            GPIO.output(self._led_pin, GPIO.LOW)
            logger.info("GPIO initialised (LED pin %d)", self._led_pin)

        if _MFRC522_AVAILABLE:
            try:
                self._reader = SimpleMFRC522()
                logger.info("MFRC522 NFC reader initialised")
            except Exception as exc:
                logger.error("Failed to initialise MFRC522: %s", exc)
                self._mode = "error"
        else:
            logger.info("NFC reader running in stub mode")

    def cleanup(self) -> None:
        """Release GPIO resources."""
        if _GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
            except Exception:
                pass
        self._mode = "idle"

    # --- LED helpers ---

    def led_on(self) -> None:
        if _GPIO_AVAILABLE:
            GPIO.output(self._led_pin, GPIO.HIGH)

    def led_off(self) -> None:
        if _GPIO_AVAILABLE:
            GPIO.output(self._led_pin, GPIO.LOW)

    def _led_blink_sync(self, count: int = 3, interval: float = 0.2) -> None:
        for _ in range(count):
            self.led_on()
            time.sleep(interval)
            self.led_off()
            time.sleep(interval)

    async def blink(self, count: int = 3) -> None:
        await asyncio.to_thread(self._led_blink_sync, count)

    # --- NFC operations ---

    async def read_tag_no_block(self) -> Optional[str]:
        """Non-blocking NFC read. Returns tag text or None."""
        if self._reader is None:
            return None
        if self._lock.locked():
            return None

        def _do_read() -> Optional[str]:
            try:
                tag_id, text = self._reader.read_no_block()
                if text is not None:
                    normalized = _normalize_text(str(text))
                    return normalized if normalized else None
                return None
            except Exception as exc:
                logger.debug("NFC read error: %s", exc)
                return None

        return await asyncio.to_thread(_do_read)

    async def write_tag_text(self, text: str, timeout_seconds: int = 30) -> None:
        """
        Wait for a tag and write text to it.
        Acquires lock so scanning is blocked during write.
        """
        async with self._lock:
            self._mode = "writing"
            self._write_cancelled = False
            logger.info("Waiting to write NFC tag: '%s'", text)

            if self._reader is None:
                # Stub: simulate write delay
                await asyncio.sleep(2)
                self._mode = "idle"
                return

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_seconds

            def _do_write() -> None:
                self._reader.write(text)

            while True:
                if self._write_cancelled:
                    self._mode = "idle"
                    raise asyncio.CancelledError("Write cancelled by user")
                if asyncio.get_running_loop().time() > deadline:
                    self._mode = "error"
                    raise TimeoutError(f"NFC write timed out after {timeout_seconds}s")

                try:
                    self.led_on()
                    await asyncio.to_thread(_do_write)
                    self.led_off()
                    self._mode = "idle"
                    logger.info("NFC tag written successfully: '%s'", text)
                    return
                except Exception as exc:
                    err_msg = str(exc).lower()
                    # MFRC522 raises when no card present; keep retrying
                    if any(kw in err_msg for kw in ("timeout", "no tag", "error", "failed")):
                        self.led_off()
                        await asyncio.sleep(0.3)
                    else:
                        self.led_off()
                        self._mode = "error"
                        raise

    def cancel_write(self) -> None:
        """Request cancellation of an in-progress write."""
        self._write_cancelled = True

    def get_status(self) -> dict:
        return {
            "mode": self._mode,
            "nfc_available": _MFRC522_AVAILABLE,
            "gpio_available": _GPIO_AVAILABLE,
            "lock_held": self._lock.locked(),
        }

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value
