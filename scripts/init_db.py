#!/usr/bin/env python3
"""Initialise the NFC Jukebox SQLite database."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nfc_jukebox import db
from nfc_jukebox.config import settings


async def main():
    db_path = settings.NFC_JUKEBOX_DB
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    await db.init_db(db_path)
    print(f"Database initialised at: {db_path}")


if __name__ == "__main__":
    asyncio.run(main())
