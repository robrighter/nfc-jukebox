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

            def _do_write_burst() -> tuple[bool, int]:
                # Tight-poll write_no_block for a short burst *inside* the worker
                # thread. This mirrors the library's blocking write() (a hot loop
                # over write_no_block), which detects a held card far more
                # reliably than polling a single attempt every 0.2s with thread
                # overhead in between. write_no_block returns a truthy tag id as
                # soon as a card responds; (None, None) when no card is present.
                # Do NOT call self._reader.write() — it blocks forever, defeating
                # the timeout/cancel checks below.
                burst_end = time.monotonic() + 0.5
                attempts = 0
                while time.monotonic() < burst_end:
                    attempts += 1
                    tag_id, _ = self._reader.write_no_block(text)
                    if tag_id is not None:
                        return True, attempts
                return False, attempts

            total_attempts = 0
            while True:
                if self._write_cancelled:
                    self.led_off()
                    self._mode = "idle"
                    raise asyncio.CancelledError("Write cancelled by user")
                if loop.time() > deadline:
                    self.led_off()
                    self._mode = "error"
                    logger.warning(
                        "NFC write timed out after %ss (%d poll attempts, no tag "
                        "detected — check the tag is seated on the reader)",
                        timeout_seconds, total_attempts,
                    )
                    raise TimeoutError(f"NFC write timed out after {timeout_seconds}s")

                try:
                    self.led_on()
                    written, attempts = await asyncio.to_thread(_do_write_burst)
                    total_attempts += attempts
                except Exception as exc:
                    # A read/write hiccup on one attempt is non-fatal; retry
                    # until the deadline rather than aborting the whole job.
                    logger.debug("NFC write attempt error: %s", exc)
                    written = False

                self.led_off()
                if written:
                    self._mode = "idle"
                    logger.info(
                        "NFC tag written successfully: '%s' (after %d poll attempts)",
                        text, total_attempts,
                    )
                    return

                # Brief yield so cancel/timeout stay responsive between bursts.
                await asyncio.sleep(0.05)

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
