"""Configuration loaded from environment / .env file."""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    AMAZON_EMAIL: str = field(default_factory=lambda: os.getenv("AMAZON_EMAIL", ""))
    AMAZON_PASSWORD: str = field(default_factory=lambda: os.getenv("AMAZON_PASSWORD", ""))
    ALEXA_DEVICE_NAME: str = field(default_factory=lambda: os.getenv("ALEXA_DEVICE_NAME", "Echo"))
    ALEXA_COMMAND_TEMPLATE: str = field(
        default_factory=lambda: os.getenv("ALEXA_COMMAND_TEMPLATE", "play the album {album}")
    )
    ALEXA_LOGIN_DATA_FILE: str = field(
        default_factory=lambda: os.getenv(
            "ALEXA_LOGIN_DATA_FILE", "/opt/nfc-jukebox/data/.alexa-login-data.json"
        )
    )
    NFC_JUKEBOX_DB: str = field(
        default_factory=lambda: os.getenv(
            "NFC_JUKEBOX_DB", "/opt/nfc-jukebox/data/nfc-jukebox.sqlite3"
        )
    )
    NFC_RESCAN_COOLDOWN_SECONDS: int = field(
        default_factory=lambda: int(os.getenv("NFC_RESCAN_COOLDOWN_SECONDS", "5"))
    )
    WEB_HOST: str = field(default_factory=lambda: os.getenv("WEB_HOST", "0.0.0.0"))
    WEB_PORT: int = field(default_factory=lambda: int(os.getenv("WEB_PORT", "8080")))
    WEB_UI_PASSWORD: str = field(default_factory=lambda: os.getenv("WEB_UI_PASSWORD", ""))
    LED_PIN: int = field(default_factory=lambda: int(os.getenv("LED_PIN", "24")))


settings = Settings()
