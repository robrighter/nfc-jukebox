"""FastAPI application with lifespan startup/shutdown."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from . import settings_store
from .alexa_client import AlexaTextCommandClient
from .amazon_setup import AmazonSetupService
from .buttons import KeyboardController
from .config import settings
from .nfc_service import NfcService
from .scanner import scanner_loop, playback_monitor

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    db_path = settings.NFC_JUKEBOX_DB
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    await db.init_db(db_path)

    nfc = NfcService(led_pin=settings.LED_PIN)
    try:
        nfc.setup()
    except Exception as exc:
        logger.error("NFC setup failed: %s", exc)

    # Prefer the device selected in the UI (stored in settings) over the .env default.
    device_name = await settings_store.get_device_name()
    alexa = AlexaTextCommandClient(
        email=settings.AMAZON_EMAIL,
        password=settings.AMAZON_PASSWORD,
        device_name=device_name,
        login_data_file=settings.ALEXA_LOGIN_DATA_FILE,
    )
    try:
        await alexa.connect()
    except Exception as exc:
        logger.error("Alexa connect failed: %s", exc)

    setup_service = AmazonSetupService(
        login_data_file=settings.ALEXA_LOGIN_DATA_FILE,
        domain=settings.AMAZON_DOMAIN,
    )

    scanner_task = asyncio.create_task(scanner_loop(nfc, alexa))

    app.state.now_playing = {"playing": False}
    monitor_task = asyncio.create_task(
        playback_monitor(nfc, alexa, app.state.now_playing)
    )

    # Physical playback buttons arrive as USB keyboard keystrokes.
    buttons = KeyboardController(alexa=alexa, key_map_spec=settings.BUTTON_KEY_MAP)
    try:
        await buttons.start()
    except Exception as exc:
        logger.error("Keyboard button setup failed: %s", exc)

    app.state.nfc = nfc
    app.state.alexa = alexa
    app.state.setup_service = setup_service
    app.state.buttons = buttons
    app.state.scanner_task = scanner_task
    app.state.monitor_task = monitor_task
    app.state.write_job: dict = {"active": False}

    logger.info("NFC Jukebox started on http://%s:%d", settings.WEB_HOST, settings.WEB_PORT)

    yield

    # --- Shutdown ---
    logger.info("NFC Jukebox shutting down...")
    scanner_task.cancel()
    monitor_task.cancel()
    for task in (scanner_task, monitor_task):
        try:
            await asyncio.wait_for(task, timeout=3)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    await buttons.stop()
    await alexa.close()
    nfc.cleanup()
    logger.info("NFC Jukebox stopped")


app = FastAPI(title="NFC Jukebox", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# Register routes after app is created
from .web import router  # noqa: E402

app.include_router(router)
