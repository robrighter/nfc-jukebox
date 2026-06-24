"""Read playback keystrokes from a USB keyboard/emulator -> Alexa media commands.

The physical play/pause, next, and previous buttons present as a USB HID
keyboard (a keyboard emulator) sending plain characters. The original firmware
read 'p' (play/pause), 'n' (next) and 'b' (previous) from stdin; we read the
same keys from the input device via evdev so it works headless under systemd.

Mapping is configured via BUTTON_KEY_MAP, e.g. "p=playpause,n=next,b=previous".
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

try:
    import evdev
    from evdev import ecodes

    _EVDEV_AVAILABLE = True
except ImportError:
    logger.warning("evdev not available — keyboard playback buttons disabled")
    _EVDEV_AVAILABLE = False


def _parse_key_map(spec: str) -> dict:
    """Parse 'p=playpause,n=next,b=previous' into {evdev_keycode: action}."""
    out: dict = {}
    if not _EVDEV_AVAILABLE:
        return out
    for pair in (spec or "").split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        char, action = pair.split("=", 1)
        char = char.strip().lower()
        action = action.strip().lower()
        if not char:
            continue
        code = ecodes.ecodes.get("KEY_" + char.upper())
        if code is None:
            logger.warning("Unknown key '%s' in BUTTON_KEY_MAP", char)
            continue
        out[code] = action
    return out


class KeyboardController:
    """Listens to USB keyboard key presses and dispatches media commands."""

    def __init__(self, alexa, key_map_spec: str) -> None:
        self._alexa = alexa
        self._code_actions = _parse_key_map(key_map_spec)
        self._devices: list = []
        self._tasks: list = []
        self._playing = True  # assume playing after a scan; toggled by play/pause

    async def start(self) -> None:
        if not _EVDEV_AVAILABLE or not self._code_actions:
            logger.info(
                "Keyboard playback buttons disabled (evdev=%s, mapped keys=%d)",
                _EVDEV_AVAILABLE,
                len(self._code_actions),
            )
            return
        try:
            paths = evdev.list_devices()
        except Exception as exc:
            logger.error("Could not list input devices: %s", exc)
            return

        wanted = set(self._code_actions)
        for path in paths:
            try:
                dev = evdev.InputDevice(path)
            except Exception:
                continue
            keys = dev.capabilities().get(ecodes.EV_KEY, [])
            if not wanted.intersection(keys):
                continue
            self._devices.append(dev)
            self._tasks.append(asyncio.create_task(self._read_loop(dev)))
            logger.info("Listening for playback keys on %s (%s)", dev.path, dev.name)

        if not self._devices:
            logger.info("No keyboard emitting the configured keys was found")

    async def _read_loop(self, dev) -> None:
        try:
            async for ev in dev.async_read_loop():
                if ev.type == ecodes.EV_KEY and ev.value == 1:  # key down
                    action = self._code_actions.get(ev.code)
                    if action:
                        await self._dispatch(action)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Keyboard read loop error on %s: %s", getattr(dev, "path", "?"), exc)

    async def _dispatch(self, action: str) -> None:
        if action == "playpause":
            media = "pause" if self._playing else "play"
            self._playing = not self._playing
        else:
            media = action
        logger.info("Playback key -> %s", media)
        try:
            await self._alexa.send_media(media)
        except Exception as exc:
            logger.error("Playback command '%s' failed: %s", media, exc)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except Exception:
                pass
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
