#!/usr/bin/env python3
"""List available Alexa devices for the configured Amazon account."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nfc_jukebox.alexa_client import AlexaTextCommandClient
from nfc_jukebox.config import settings


async def main():
    client = AlexaTextCommandClient(
        email=settings.AMAZON_EMAIL,
        password=settings.AMAZON_PASSWORD,
        device_name=settings.ALEXA_DEVICE_NAME,
        login_data_file=settings.ALEXA_LOGIN_DATA_FILE,
    )
    print("Connecting to Amazon/Alexa...")
    await client.connect()

    if not client.connected:
        print(
            "\nNot connected. Connect your Amazon account first via the web UI:\n"
            "  http://nfc-jukebox.local:8080/setup\n"
            "(passkey supported — no password is stored on the Pi)."
        )
        await client.close()
        return

    devices = await client.list_devices()
    if devices:
        print("\nAvailable Alexa devices:")
        for name in devices:
            print(f"  - {name}")
    else:
        print("No devices found.")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
