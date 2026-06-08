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
from .alexa_client import AlexaTextCommandClient
from .config import settings
from .nfc_service import NfcService
from .scanner import scanner_loop

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

    alexa = AlexaTextCommandClient(
        email=settings.AMAZON_EMAIL,
        password=settings.AMAZON_PASSWORD,
        device_name=settings.ALEXA_DEVICE_NAME,
        login_data_file=settings.ALEXA_LOGIN_DATA_FILE,
    )
    try:
        await alexa.connect()
    except Exception as exc:
        logger.error("Alexa connect failed: %s", exc)

    scanner_task = asyncio.create_task(scanner_loop(nfc, alexa))

    app.state.nfc = nfc
    app.state.alexa = alexa
    app.state.scanner_task = scanner_task
    app.state.write_job: dict = {"active": False}

    logger.info("NFC Jukebox started on http://%s:%d", settings.WEB_HOST, settings.WEB_PORT)

    yield

    # --- Shutdown ---
    logger.info("NFC Jukebox shutting down...")
    scanner_task.cancel()
    try:
        await asyncio.wait_for(scanner_task, timeout=3)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    await alexa.close()
    nfc.cleanup()
    logger.info("NFC Jukebox stopped")


app = FastAPI(title="NFC Jukebox", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# Register routes after app is created
from .web import router  # noqa: E402

app.include_router(router)
