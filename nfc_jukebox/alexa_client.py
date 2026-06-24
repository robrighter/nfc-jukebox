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
            await self._api.login.login_mode_stored_data()

            await self._find_device()
            self._connected = True
            logger.info("Connected to Alexa. Target device: %s", self._device_name)

        except Exception as exc:
            logger.error("Failed to connect to Alexa: %s", exc)
            self._connected = False

    async def _fetch_devices(self) -> list:
        """Return the account's devices using the LIGHT base-devices call.

        get_devices_data() also fetches DND/notifications/communication
        preferences; that communications call frequently fails for some
        accounts and retries with growing backoff, hanging startup for
        minutes. We only need names + serials, so use get_base_devices().
        """
        await self._api._device_handler.get_base_devices()  # type: ignore[attr-defined]
        return list(self._api._device_handler.devices.values())  # type: ignore[attr-defined]

    async def _find_device(self) -> None:
        """Locate the configured device in the account device list."""
        if self._api is None:
            return
        try:
            devices = await self._fetch_devices()
            target = self._device_name.lower()

            for device in devices:
                if device.account_name.lower() == target:
                    self._target_device = device
                    return

            # Fallback: partial match
            for device in devices:
                if target in device.account_name.lower():
                    self._target_device = device
                    logger.warning(
                        "Exact device '%s' not found; using '%s'",
                        self._device_name,
                        device.account_name,
                    )
                    return

            logger.warning(
                "Device '%s' not found. Available: %s",
                self._device_name,
                [d.account_name for d in devices],
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
            devices = await self._fetch_devices()
            return sorted(d.account_name for d in devices)
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

    async def get_now_playing(self) -> dict:
        """Return current playback info for the target device.

        {playing: bool, state: str|None, title, artist, album, art}
        """
        result = {
            "playing": False,
            "state": None,
            "title": None,
            "artist": None,
            "album": None,
            "art": None,
        }
        if not self._connected or self._api is None or self._target_device is None:
            return result
        try:
            await self._api.sync_media_state()
            states = await self._api._media_handler.media_states
            st = states.get(self._target_device.serial_number)
            if st is not None:
                result.update(
                    playing=(st.player_state == "PLAYING"),
                    state=st.player_state,
                    title=st.now_playing_title,
                    artist=st.now_playing_line1,
                    album=st.now_playing_line2,
                    art=st.now_playing_url,
                )
        except Exception as exc:
            logger.debug("now-playing fetch failed: %s", exc)
        return result

    # Map our action names to the library's media-control enum members.
    _MEDIA_ACTIONS = {"play", "pause", "next", "previous", "stop"}

    async def send_media(self, action: str) -> None:
        """Send a playback control (play/pause/next/previous/stop) to the device."""
        action = action.lower().strip()
        if action not in self._MEDIA_ACTIONS:
            raise ValueError(f"Unknown media action: {action!r}")
        if not self._connected or self._api is None:
            raise RuntimeError("Alexa client is not connected")
        if self._target_device is None:
            raise RuntimeError(
                f"Target device '{self._device_name}' not found in account"
            )
        from aioamazondevices.structures import AmazonMediaControls  # type: ignore

        control = {
            "play": AmazonMediaControls.Play,
            "pause": AmazonMediaControls.Pause,
            "next": AmazonMediaControls.Next,
            "previous": AmazonMediaControls.Previous,
            "stop": AmazonMediaControls.Stop,
        }[action]
        try:
            if action == "stop":
                await self._api.send_media_command(self._target_device, control)
            else:
                # Work around an aioamazondevices 14.1.3 bug: URI_MEDIA_CONTROL
                # ("api/np/command") lacks a leading slash, so the library builds
                # https://alexa.amazon.comapi/np/command (bad host). Build the
                # request ourselves with a correct URL via the http wrapper.
                await self._send_np_command(control.value)
            logger.info("Sent media command: %s", action)
        except Exception as exc:
            logger.error("Failed to send media command '%s': %s", action, exc)
            raise

    async def _send_np_command(self, command_type: str) -> None:
        """POST a now-playing transport command with a correctly-built URL."""
        from http import HTTPMethod

        from yarl import URL

        device = self._target_device
        domain = self._api._session_state_data.domain  # type: ignore[attr-defined]
        url = (
            URL.build(scheme="https", host=f"alexa.amazon.{domain}")
            .joinpath("api/np/command")
            .with_query(
                deviceSerialNumber=device.serial_number,
                deviceType=device.device_type,
            )
        )
        await self._api._http_wrapper.session_request(  # type: ignore[attr-defined]
            method=HTTPMethod.POST,
            url=url,
            input_data={"type": command_type},
            json_data=True,
        )

    async def set_device(self, name: str) -> bool:
        """Change the target Echo device by name. Returns True if found."""
        self._device_name = name
        self._target_device = None
        if self._connected:
            await self._find_device()
        return self._target_device is not None

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def connected(self) -> bool:
        return self._connected
