#!/usr/bin/env python3
"""Validate the two aioamazondevices integration points on real hardware.

Run this ON THE PI (Python 3.12+, requirements installed) before relying on the
web /setup flow. It exercises exactly the two library-dependent calls in
nfc_jukebox/amazon_setup.py — nothing else — so you can confirm the pinned
library version behaves as expected and, if not, see precisely what to fix.

Usage:
    cd /opt/nfc-jukebox
    .venv/bin/python scripts/verify_amazon_setup.py

What it does:
    1. Checks Python version and that aioamazondevices imports.
    2. INTEGRATION POINT 1 — generates a PKCE verifier + Amazon sign-in URL.
       You open the URL in a browser, sign in (passkey OK), and paste back the
       resulting .../ap/maplanding?... URL.
    3. INTEGRATION POINT 2 — exchanges the authorization code for device tokens
       and prints which login_data keys came back (tokens are NOT printed).

Nothing is written to disk unless you pass --save, in which case it writes to
ALEXA_LOGIN_DATA_FILE just like the real flow.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nfc_jukebox.amazon_setup import (  # noqa: E402
    AmazonSetupService,
    AmazonSetupError,
    _extract_authorization_code,
)
from nfc_jukebox.config import settings  # noqa: E402

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET}   {msg}")


def fail(msg: str) -> None:
    print(f"{RED}[FAIL]{RESET} {msg}")


def info(msg: str) -> None:
    print(f"{YELLOW}[..]{RESET}   {msg}")


async def main(save: bool) -> int:
    print("=== NFC Jukebox — Amazon setup integration check ===\n")

    # --- Preflight ---
    if sys.version_info < (3, 12):
        fail(
            f"Python {sys.version_info.major}.{sys.version_info.minor} detected. "
            "aioamazondevices requires 3.12+. Use Raspberry Pi OS Trixie."
        )
        return 1
    ok(f"Python {sys.version_info.major}.{sys.version_info.minor}")

    try:
        import aioamazondevices  # noqa: F401

        version = getattr(aioamazondevices, "__version__", "unknown")
        ok(f"aioamazondevices import (version: {version})")
    except ImportError as exc:
        fail(f"aioamazondevices not importable: {exc}")
        return 1

    service = AmazonSetupService(
        login_data_file=settings.ALEXA_LOGIN_DATA_FILE,
        domain=settings.AMAZON_DOMAIN,
    )

    # --- Integration point 1: build sign-in URL ---
    print(f"\n--- INTEGRATION POINT 1: build sign-in URL ---")
    try:
        login_url = await service.begin_login()
    except AmazonSetupError as exc:
        fail(f"begin_login() failed: {exc}")
        print(
            "\nFix: check _build_login_url() in nfc_jukebox/amazon_setup.py "
            "against this library version's login.py."
        )
        return 1
    except Exception as exc:
        fail(f"Unexpected error in begin_login(): {exc}")
        return 1

    if "amazon" not in login_url or "openid" not in login_url:
        fail(f"URL doesn't look like an Amazon OAuth URL:\n  {login_url}")
        return 1
    ok("Generated sign-in URL")
    print(f"\n{login_url}\n")

    # --- Manual browser step ---
    print("Open the URL above in a browser, sign in (passkey OK), then copy")
    print("the FULL address-bar URL you land on (contains 'maplanding').\n")
    redirect_url = input("Paste the redirect URL here (or blank to stop): ").strip()
    if not redirect_url:
        info("Stopped before completion. Point 1 verified; point 2 untested.")
        return 0

    code = _extract_authorization_code(redirect_url)
    if not code:
        fail("No authorization code found in that URL.")
        print("Expected a parameter named 'openid.oa2.authorization_code'.")
        return 1
    ok(f"Extracted authorization code ({code[:8]}…)")

    # --- Integration point 2: register device ---
    print(f"\n--- INTEGRATION POINT 2: register device ---")
    try:
        login_data = await service.complete_login(redirect_url)
    except AmazonSetupError as exc:
        fail(f"complete_login() failed: {exc}")
        print(
            "\nFix: check _register_device() in nfc_jukebox/amazon_setup.py "
            "against this library version's login.py."
        )
        return 1
    except Exception as exc:
        fail(f"Unexpected error in complete_login(): {exc}")
        return 1

    expected = {"access_token", "refresh_token", "adp_token", "device_private_key"}
    present = expected & set(login_data.keys())
    ok(f"Registration returned login data with keys: {sorted(login_data.keys())}")
    if present:
        ok(f"Found expected token keys: {sorted(present)}")
    else:
        fail(
            "None of the expected token keys were present — the saved session "
            "may not work. Inspect the returned structure."
        )
        return 1

    if save:
        ok(f"Saved login data to {settings.ALEXA_LOGIN_DATA_FILE}")
    else:
        # complete_login already wrote the file; remove it unless --save.
        try:
            os.remove(settings.ALEXA_LOGIN_DATA_FILE)
            info("Did not keep login data (pass --save to persist).")
        except OSError:
            pass

    print(f"\n{GREEN}Both integration points verified.{RESET} The /setup flow should work.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist the login data on success (default: discard after check)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.save)))
