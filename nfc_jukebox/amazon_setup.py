"""Passkey-friendly Amazon login setup flow.

This module implements a browser-based OAuth setup so the user can sign in to
Amazon with a passkey (or any normal login) in their own browser — the
Raspberry Pi never sees the password. Only revocable device tokens are stored.

Flow
----
1. ``begin_login()`` generates a PKCE ``code_verifier`` and builds an Amazon
   sign-in URL. The user opens this URL in their own browser and signs in
   (passkey works here because it is a real browser).
2. Amazon redirects to ``https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code=...``.
   The user copies that final URL back into the setup page.
3. ``complete_login()`` extracts the authorization code and exchanges it
   (together with the stored ``code_verifier``) for device tokens, then writes
   the resulting login-data JSON to disk.

================================ IMPORTANT ================================
The two functions marked `# >>> LIBRARY INTEGRATION POINT` below drive
`aioamazondevices`' OAuth machinery. The exact method names / constructor
signature depend on the installed library version and MUST be verified on the
Pi against the pinned version in requirements.txt. Everything else in the app
(web routes, PKCE state, token persistence, client reconnect) is
version-independent and complete.

Verified against the OAuth/PKCE flow documented in aioamazondevices `login.py`:
the library builds an `openid.oa2.response_type=code` URL with an S256 PKCE
challenge, returns to `/ap/maplanding`, and registers the device by POSTing
`authorization_code` + `code_verifier` to Amazon's `/auth/register` endpoint.
==========================================================================
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

# Pending logins older than this are treated as expired.
_PENDING_TTL_SECONDS = 30 * 60

logger = logging.getLogger(__name__)

# Default Amazon marketplace domain. Override via AMAZON_DOMAIN if needed
# (e.g. "co.uk", "de"). Most users are on "com".
DEFAULT_DOMAIN = "com"


class AmazonSetupError(RuntimeError):
    """Raised when the setup flow cannot complete."""


def _import_api():
    """Import AmazonEchoApi, raising a friendly error if it's missing."""
    try:
        from aioamazondevices.api import AmazonEchoApi  # type: ignore

        return AmazonEchoApi
    except ImportError as exc:  # pragma: no cover - depends on Pi env
        raise AmazonSetupError(
            "aioamazondevices is not installed. Install requirements on a "
            "Python 3.12+ runtime (Raspberry Pi OS Trixie ships 3.13)."
        ) from exc


@dataclass
class PendingLogin:
    """In-memory state for an in-progress login. Never persisted."""

    code_verifier: str
    login_url: str
    domain: str
    serial: str  # device serial; MUST be reused at registration time


class AmazonSetupService:
    """Drives the browser-based, passkey-friendly Amazon login."""

    def __init__(self, login_data_file: str, domain: str = DEFAULT_DOMAIN) -> None:
        self._login_data_file = login_data_file
        self._domain = domain
        self._pending: Optional[PendingLogin] = None
        # Persist the in-progress login so a service restart between "start"
        # and "finish" doesn't lose it.
        self._pending_file = str(
            Path(login_data_file).parent / ".alexa-setup-pending.json"
        )

    # ------------------------------------------------------------------ #
    # Public state helpers
    # ------------------------------------------------------------------ #

    def is_complete(self) -> bool:
        """True if saved login data already exists on disk."""
        path = Path(self._login_data_file)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            return bool(data.get("access_token") or data.get("refresh_token"))
        except Exception:
            return False

    @property
    def pending(self) -> Optional[PendingLogin]:
        if self._pending is None:
            self._pending = self._load_pending()
        return self._pending

    # ------------------------------------------------------------------ #
    # Pending-login persistence (survives a service restart mid-flow)
    # ------------------------------------------------------------------ #

    def _save_pending(self) -> None:
        if self._pending is None:
            return
        data = asdict(self._pending)
        data["_ts"] = time.time()
        path = Path(self._pending_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
            path.chmod(0o600)
        except (OSError, NotImplementedError) as exc:
            logger.warning("Could not persist pending login: %s", exc)

    def _load_pending(self) -> Optional[PendingLogin]:
        path = Path(self._pending_file)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except Exception:
            return None
        if time.time() - data.get("_ts", 0) > _PENDING_TTL_SECONDS:
            self._clear_pending()
            return None
        data.pop("_ts", None)
        try:
            return PendingLogin(**data)
        except TypeError:
            return None

    def _clear_pending(self) -> None:
        self._pending = None
        try:
            Path(self._pending_file).unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Step 1: build the sign-in URL
    # ------------------------------------------------------------------ #

    async def begin_login(self) -> str:
        """Generate a PKCE verifier + Amazon sign-in URL.

        Returns the URL the user should open in their own browser.
        """
        code_verifier, login_url, serial = await self._build_login_url(self._domain)
        self._pending = PendingLogin(
            code_verifier=code_verifier,
            login_url=login_url,
            domain=self._domain,
            serial=serial,
        )
        self._save_pending()
        logger.info("Amazon setup: generated sign-in URL (domain=%s)", self._domain)
        return login_url

    # ------------------------------------------------------------------ #
    # Step 2: complete with the redirect URL the user pastes back
    # ------------------------------------------------------------------ #

    async def complete_login(self, redirect_url: str) -> dict[str, Any]:
        """Exchange the authorization code in ``redirect_url`` for tokens.

        ``redirect_url`` is the full ``.../ap/maplanding?...`` URL the user
        copied from their browser after signing in. Saves login data on success.
        """
        if self._pending is None:
            self._pending = self._load_pending()
        if self._pending is None:
            raise AmazonSetupError(
                "No login in progress. Start the setup flow again."
            )

        code = _extract_authorization_code(redirect_url)
        if not code:
            raise AmazonSetupError(
                "Could not find an authorization code in that URL. Make sure you "
                "copied the full address bar after signing in (it should contain "
                "'openid.oa2.authorization_code')."
            )

        login_data = await self._register_device(code)

        self._save_login_data(login_data)
        self._clear_pending()
        logger.info("Amazon setup: registration complete, tokens saved")
        return login_data

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _save_login_data(self, login_data: dict[str, Any]) -> None:
        path = Path(self._login_data_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(login_data, indent=2))
        # Tighten perms where the platform supports it (POSIX).
        try:
            path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass

    # ================================================================== #
    # Library integration (verified against aioamazondevices 14.1.3)      #
    # ================================================================== #
    async def _build_login_url(self, domain: str) -> tuple[str, str, str]:
        """Return (code_verifier, login_url, serial).

        Drives aioamazondevices' AmazonLogin (``api.login``). Pass
        ``login_data=None`` so a fresh device serial is generated — a non-empty
        login_data makes the library look up ``login_data['device_info']`` and
        raise KeyError. The generated serial is returned so registration can
        reuse it (the authorization code is bound to that device id).
        """
        AmazonEchoApi = _import_api()
        import aiohttp

        async with aiohttp.ClientSession() as session:
            api = AmazonEchoApi(session, "", "", login_data=None)
            login = api.login
            try:
                code_verifier = login._create_code_verifier()  # bytes
                client_id = login._build_client_id()
                url = login._build_oauth_url(code_verifier, client_id)
                serial = login._serial
            except (AttributeError, KeyError) as exc:
                raise AmazonSetupError(
                    "aioamazondevices internals differ from the expected "
                    f"(14.1.3) shape: {exc!r}. Check api.login methods "
                    "_create_code_verifier / _build_client_id / _build_oauth_url."
                ) from exc

            return code_verifier.decode(), str(url), serial

    async def _register_device(self, authorization_code: str) -> dict[str, Any]:
        """Exchange the authorization code for device tokens (login_data dict).

        Reuses the serial from the URL-build step (stored on ``_pending``) and
        passes the PKCE verifier as bytes, matching AmazonLogin._register_device.
        """
        if self._pending is None:
            raise AmazonSetupError("No login in progress.")

        AmazonEchoApi = _import_api()
        import aiohttp

        async with aiohttp.ClientSession() as session:
            api = AmazonEchoApi(session, "", "", login_data=None)
            login = api.login
            # The authorization code was issued for device:{serial}; the
            # registration must present the SAME serial/client_id.
            login._serial = self._pending.serial
            try:
                login_data = await login._register_device(
                    {
                        "authorization_code": authorization_code,
                        "code_verifier": self._pending.code_verifier.encode(),
                    }
                )
            except AmazonSetupError:
                raise
            except Exception as exc:
                raise AmazonSetupError(f"Device registration failed: {exc}") from exc

            if not isinstance(login_data, dict):
                raise AmazonSetupError(
                    "Registration returned an unexpected result; expected a "
                    "login-data dict."
                )
            return login_data


def _extract_authorization_code(redirect_url: str) -> Optional[str]:
    """Pull ``openid.oa2.authorization_code`` out of a maplanding redirect URL.

    Version-independent and fully testable. Accepts either the full redirect
    URL or a bare ``code=`` style value.
    """
    from urllib.parse import parse_qs, urlparse

    redirect_url = (redirect_url or "").strip()
    if not redirect_url:
        return None

    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    for key in ("openid.oa2.authorization_code", "authorization_code", "code"):
        if key in params and params[key]:
            return params[key][0]
    return None
