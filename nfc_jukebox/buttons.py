"""Physical playback buttons wired to GPIO -> Alexa media commands.

Buttons are wired between a GPIO pin and GND; we enable the internal pull-up
and trigger on the falling edge (press). Each press dispatches a media command
to the Alexa client. The play/pause button toggles between play and pause.

Pins are configured in .env (BCM numbering); 0/blank disables a button.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO  # type: ignore

    _GPIO_AVAILABLE = True
except ImportError:
    logger.warning("RPi.GPIO not available — physical buttons disabled (stub mode)")
    _GPIO_AVAILABLE = False
    GPIO = None  # type: ignore


class ButtonController:
    def __init__(
        self,
        alexa,
        loop: asyncio.AbstractEventLoop,
        playpause_pin: int = 0,
        next_pin: int = 0,
        previous_pin: int = 0,
    ) -> None:
        self._alexa = alexa
        self._loop = loop
        self._playpause_pin = playpause_pin
        self._next_pin = next_pin
        self._previous_pin = previous_pin
        self._playing = True  # assume something is playing after a scan
        self._configured_pins: list[int] = []

    def setup(self) -> None:
        if not _GPIO_AVAILABLE:
            return
        # nfc_service already set BCM mode; setting again is harmless.
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        pin_actions = {
            self._playpause_pin: "playpause",
            self._next_pin: "next",
            self._previous_pin: "previous",
        }
        for pin, action in pin_actions.items():
            if not pin:
                continue
            try:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.add_event_detect(
                    pin,
                    GPIO.FALLING,
                    callback=self._make_callback(action),
                    bouncetime=300,
                )
                self._configured_pins.append(pin)
                logger.info("Button '%s' wired to GPIO %d", action, pin)
            except Exception as exc:
                logger.error("Failed to set up button '%s' on GPIO %d: %s", action, pin, exc)

        if not self._configured_pins:
            logger.info("No physical buttons configured (set BUTTON_*_PIN in .env)")

    def cleanup(self) -> None:
        if not _GPIO_AVAILABLE:
            return
        for pin in self._configured_pins:
            try:
                GPIO.remove_event_detect(pin)
            except Exception:
                pass

    def _make_callback(self, action: str):
        def _cb(_channel) -> None:
            # Runs in RPi.GPIO's thread; hop back to the event loop.
            try:
                asyncio.run_coroutine_threadsafe(self._dispatch(action), self._loop)
            except Exception as exc:
                logger.error("Button dispatch failed for '%s': %s", action, exc)

        return _cb

    async def _dispatch(self, action: str) -> None:
        if action == "playpause":
            media_action = "pause" if self._playing else "play"
            self._playing = not self._playing
        else:
            media_action = action
        logger.info("Button pressed: %s -> %s", action, media_action)
        try:
            await self._alexa.send_media(media_action)
        except Exception as exc:
            logger.error("Button '%s' command failed: %s", action, exc)
