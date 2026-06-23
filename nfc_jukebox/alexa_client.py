"""Alexa text command client using aioamazondevices."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AlexaTextCommandClient:
    """Sends text commands to an Amazon Echo device."""

    def __init__(
        self,
        email: str,
        password: str,
        device_name: str,
        login_data_file: str,
    ) -> None:
        self._email = email
        self._password = password
        self._device_name = device_name
        self._login_data_file = login_data_file
        self._api: Optional[object] = None
        self._session: Optional[object] = None
        self._target_device: Optional[object] = None
        self._connected: bool = False

    async def connect(self) -> None:
        """Connect to Alexa using saved login data (passkey setup flow).

        Credentials are NOT required or used here. The browser-based setup flow
        (see amazon_setup.py and /setup) produces the saved login-data file;
        this method simply resumes that session. If no saved session exists,
        the client stays disconnected and the web UI prompts the user to run
        setup — the app keeps running either way.
        """
        login_data_path = Path(self._login_data_file)
        if not login_data_path.exists():
            logger.warning(
                "No saved Amazon login data at %s — visit /setup to connect your "
                "Amazon account (passkey supported).",
                login_data_path,
            )
            return

        try:
            from aioamazondevices.api import AmazonEchoApi  # type: ignore
        except ImportError:
            logger.error(
                "aioamazondevices is not installed. Install requirements on a "
                "Python 3.12+ runtime (Raspberry Pi OS Trixie ships 3.13)."
            )
            return

        try:
            login_data = json.loads(login_data_path.read_text())
        except Exception as exc:
            logger.error("Failed to read saved login data: %s", exc)
            return

        try:
            import aiohttp

            self._session = aiohttp.ClientSession()
            # >>> LIBRARY INTEGRATION POINT: resume session from saved tokens.
            # VERIFY ON PI against pinned aioamazondevices version. Researched
            # constructor: AmazonEchoApi(client_session, login_email,
            # login_password, login_data=..., save_to_file=...), with
            # login_mode_stored_data() to resume from saved tokens.
            self._api = AmazonEchoApi(
                self._session,
                self._email or "",
                self._password or "",
                login_data=login_data,
            )
            await self._api.login_mode_stored_data()

            await self._find_device()
            self._connected = True
            logger.info("Connected to Alexa. Target device: %s", self._device_name)

        except Exception as exc:
            logger.error("Failed to connect to Alexa: %s", exc)
            self._connected = False

    async def _find_device(self) -> None:
        """Locate the configured device in the account device list."""
        if self._api is None:
            return
        try:
            devices = await self._api.get_devices_data()
            device_map: dict = {}
            if isinstance(devices, dict):
                device_map = devices
            elif isinstance(devices, list):
                device_map = {d.get("accountName", str(i)): d for i, d in enumerate(devices)}

            for key, device in device_map.items():
                name = key if isinstance(key, str) else str(key)
                if name.lower() == self._device_name.lower():
                    self._target_device = device
                    return

            # Fallback: partial match
            for key, device in device_map.items():
                name = key if isinstance(key, str) else str(key)
                if self._device_name.lower() in name.lower():
                    self._target_device = device
                    logger.warning(
                        "Exact device '%s' not found; using '%s'",
                        self._device_name,
                        name,
                    )
                    return

            logger.warning(
                "Device '%s' not found. Available: %s",
                self._device_name,
                list(device_map.keys()),
            )
        except Exception as exc:
            logger.error("Error fetching device list: %s", exc)

    async def close(self) -> None:
        """Close the API session."""
        if self._api is not None:
            try:
                await self._api.close()
            except Exception as exc:
                logger.debug("Error closing Alexa API: %s", exc)
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as exc:
                logger.debug("Error closing aiohttp session: %s", exc)
            self._session = None
        self._connected = False

    async def reconnect(self) -> None:
        """Tear down and reconnect — used after setup completes."""
        await self.close()
        self._api = None
        self._target_device = None
        await self.connect()

    async def list_devices(self) -> list[str]:
        """Return list of device names in the account."""
        if self._api is None:
            return []
        try:
            devices = await self._api.get_devices_data()
            if isinstance(devices, dict):
                return list(devices.keys())
            if isinstance(devices, list):
                return [d.get("accountName", str(i)) for i, d in enumerate(devices)]
        except Exception as exc:
            logger.error("Failed to list devices: %s", exc)
        return []

    async def send_text_command(self, text_command: str) -> None:
        """Send a text command to the configured Echo device."""
        if not self._connected or self._api is None:
            raise RuntimeError("Alexa client is not connected")
        if self._target_device is None:
            raise RuntimeError(
                f"Target device '{self._device_name}' not found in account"
            )
        try:
            await self._api.call_alexa_text_command(self._target_device, text_command)
            logger.info("Sent Alexa command: %s", text_command)
        except Exception as exc:
            logger.error("Failed to send Alexa command '%s': %s", text_command, exc)
            raise

    @property
    def connected(self) -> bool:
        return self._connected
