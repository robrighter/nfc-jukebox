"""Background NFC scanner task."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

from . import db
from .alexa_client import AlexaTextCommandClient
from .config import settings
from .nfc_service import NfcService
from .settings_store import get_command_template

logger = logging.getLogger(__name__)


def build_command(template: str, album: str, artist: str = "") -> str:
    """Format the Alexa command from a template using {album} and {artist}.

    When no artist is known, a dangling 'by' (from 'by {artist}') is removed so
    the command reads naturally.
    """
    try:
        command = template.format(album=album, artist=artist or "")
    except (KeyError, ValueError, IndexError):
        command = f"play the album {album}"
    if not artist:
        command = re.sub(r"\s+by\s*$", "", command)
    return re.sub(r"\s{2,}", " ", command).strip()


async def playback_monitor(
    nfc: NfcService,
    alexa: AlexaTextCommandClient,
    store: dict,
    interval: float = 8.0,
) -> None:
    """Poll Alexa playback state; light the LED while a song is playing.

    Mirrors the original behaviour (LED on during playback). Updates ``store``
    in place so the web UI can show "now playing" without extra API calls.
    """
    logger.info("Playback monitor started (interval=%ss)", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            # Don't fight the writer for the LED / reader.
            if nfc.mode == "writing":
                continue
            np = await alexa.get_now_playing()
            store.clear()
            store.update(np)
            if np.get("playing"):
                nfc.led_on()
            else:
                nfc.led_off()
        except asyncio.CancelledError:
            logger.info("Playback monitor stopped")
            return
        except Exception as exc:
            logger.debug("Playback monitor error: %s", exc)


async def scanner_loop(
    nfc: NfcService,
    alexa: AlexaTextCommandClient,
) -> None:
    """
    Continuously poll the NFC reader and dispatch Alexa commands.
    Runs until cancelled.
    """
    last_scanned: dict[str, float] = {}  # album_text -> timestamp
    cooldown = settings.NFC_RESCAN_COOLDOWN_SECONDS

    logger.info("NFC scanner started (cooldown=%ds)", cooldown)

    while True:
        try:
            await asyncio.sleep(0.2)

            # Skip if NFC is in write mode
            if nfc.mode == "writing":
                continue

            nfc.mode = "scanning"
            tag_text: Optional[str] = await nfc.read_tag_no_block()

            if not tag_text:
                if nfc.mode == "scanning":
                    nfc.mode = "idle"
                continue

            # Cooldown deduplication
            now = time.monotonic()
            if tag_text in last_scanned:
                elapsed = now - last_scanned[tag_text]
                if elapsed < cooldown:
                    logger.debug(
                        "Ignoring duplicate scan of '%s' (%.1fs ago)", tag_text, elapsed
                    )
                    nfc.mode = "idle"
                    continue

            last_scanned[tag_text] = now

            # Build command from current template. Resolve the artist from the
            # album record (user-set, else iTunes metadata) for {artist}.
            template = await get_command_template()
            album_row = await db.get_album_by_text(tag_text)
            artist = ""
            if album_row:
                artist = album_row.get("artist") or album_row.get("meta_artist") or ""
            command = build_command(template, tag_text, artist)

            logger.info("NFC tag scanned: '%s' -> '%s'", tag_text, command)

            # Send to Alexa
            status = "success"
            error_msg: Optional[str] = None

            nfc.led_on()
            try:
                await alexa.send_text_command(command)
            except Exception as exc:
                error_msg = str(exc)
                status = "error"
                logger.error("Alexa command failed: %s", exc)
                await nfc.blink(3)
            else:
                # Leave the LED on — playback is starting; the playback monitor
                # keeps it in sync with the real play/pause state from here.
                pass

            # Log to DB
            await db.add_scan_history(tag_text, command, status, error_msg)
            await db.mark_album_scanned(tag_text)

            nfc.mode = "idle"

        except asyncio.CancelledError:
            logger.info("NFC scanner stopped")
            nfc.mode = "idle"
            return
        except Exception as exc:
            logger.error("Unexpected scanner error: %s", exc, exc_info=True)
            nfc.mode = "idle"
            await asyncio.sleep(1)
