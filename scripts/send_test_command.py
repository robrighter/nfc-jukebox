#!/usr/bin/env python3
"""Send a test text command to the configured Alexa device.

Usage:
    python scripts/send_test_command.py "play the album Abbey Road by The Beatles"
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nfc_jukebox.alexa_client import AlexaTextCommandClient
from nfc_jukebox.config import settings


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_test_command.py \"<command>\"")
        sys.exit(1)

    command = sys.argv[1]

    client = AlexaTextCommandClient(
        email=settings.AMAZON_EMAIL,
        password=settings.AMAZON_PASSWORD,
        device_name=settings.ALEXA_DEVICE_NAME,
        login_data_file=settings.ALEXA_LOGIN_DATA_FILE,
    )
    print(f"Connecting to Amazon/Alexa...")
    await client.connect()

    print(f"Sending command: {command!r}")
    try:
        await client.send_text_command(command)
        print("Command sent successfully.")
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
