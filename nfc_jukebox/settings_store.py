"""Wrapper for reading/writing app settings from the database."""
import logging

from . import db
from .config import settings as env_settings

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_TEMPLATE = env_settings.ALEXA_COMMAND_TEMPLATE or "play the album {album}"
DEFAULT_DEVICE_NAME = env_settings.ALEXA_DEVICE_NAME or "Echo"


async def get_device_name() -> str:
    value = await db.get_setting("alexa_device_name")
    return value if value else DEFAULT_DEVICE_NAME


async def set_device_name(name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Device name must not be empty")
    await db.set_setting("alexa_device_name", name)
    logger.info("Alexa device set to: %s", name)


async def get_command_template() -> str:
    value = await db.get_setting("alexa_command_template")
    if value is None:
        await db.set_setting("alexa_command_template", DEFAULT_COMMAND_TEMPLATE)
        return DEFAULT_COMMAND_TEMPLATE
    return value


async def set_command_template(template: str) -> None:
    if not template.strip():
        raise ValueError("Template must not be empty")
    if "{album}" not in template:
        raise ValueError("Template must contain {album} placeholder")
    # Validate no unknown placeholders
    try:
        template.format(album="test")
    except (KeyError, ValueError, IndexError) as exc:
        raise ValueError(f"Template contains invalid placeholders: {exc}") from exc
    await db.set_setting("alexa_command_template", template)
    logger.info("Command template updated to: %s", template)


async def get_all() -> dict[str, str]:
    stored = await db.get_all_settings()
    if "alexa_command_template" not in stored:
        stored["alexa_command_template"] = DEFAULT_COMMAND_TEMPLATE
    return stored
