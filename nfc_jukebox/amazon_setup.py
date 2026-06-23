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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default Amazon marketplace domain. Override via AMAZON_DOMAIN if needed
# (e.g. "co.uk", "de"). Most users are on "com".
DEFAULT_DOMAIN = "com"


class AmazonSetupError(RuntimeError):
    """Raised when the setup flow cannot complete."""


@dataclass
class PendingLogin:
    """In-memory state for an in-progress login. Never persisted."""

    code_verifier: str
    login_url: str
    domain: str


class AmazonSetupService:
    """Drives the browser-based, passkey-friendly Amazon login."""

    def __init__(self, login_data_file: str, domain: str = DEFAULT_DOMAIN) -> None:
        self._login_data_file = login_data_file
        self._domain = domain
        self._pending: Optional[PendingLogin] = None

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
        return self._pending

    # ------------------------------------------------------------------ #
    # Step 1: build the sign-in URL
    # ------------------------------------------------------------------ #

    async def begin_login(self) -> str:
        """Generate a PKCE verifier + Amazon sign-in URL.

        Returns the URL the user should open in their own browser.
        """
        code_verifier, login_url = await self._build_login_url(self._domain)
        self._pending = PendingLogin(
            code_verifier=code_verifier,
            login_url=login_url,
            domain=self._domain,
        )
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

        login_data = await self._register_device(
            authorization_code=code,
            code_verifier=self._pending.code_verifier,
            domain=self._pending.domain,
        )

        self._save_login_data(login_data)
        self._pending = None
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
    # >>> LIBRARY INTEGRATION POINT 1: build OAuth URL                    #
    # ================================================================== #
    async def _build_login_url(self, domain: str) -> tuple[str, str]:
        """Return (code_verifier, login_url).

        VERIFY ON PI: confirm these aioamazondevices internals against the
        pinned version. As of the researched source, login.py exposes:
          - _create_code_verifier(length=32) -> bytes
          - _build_client_id() -> str
          - _build_oauth_url(code_verifier, client_id, registration_language)
            -> yarl.URL  (an openid.oa2 'code' flow URL returning to
               /ap/maplanding with an S256 code_challenge)
        If the names differ, adapt here only — the rest of the app is stable.
        """
        try:
            import aiohttp
            from aioamazondevices.api import AmazonEchoApi  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on Pi env
            raise AmazonSetupError(
                "aioamazondevices is not installed. Install requirements on a "
                "Python 3.12+ runtime (Raspberry Pi OS Trixie ships 3.13)."
            ) from exc

        async with aiohttp.ClientSession() as session:
            # Email/password are not used for the browser flow; pass blanks.
            api = AmazonEchoApi(session, "", "", login_data={"site": f"https://www.amazon.{domain}"})
            try:
                code_verifier = api._create_code_verifier()  # type: ignore[attr-defined]
                client_id = api._build_client_id()  # type: ignore[attr-defined]
                url = api._build_oauth_url(code_verifier, client_id)  # type: ignore[attr-defined]
            except AttributeError as exc:
                raise AmazonSetupError(
                    "The installed aioamazondevices version exposes different "
                    "internal methods than expected. Verify _create_code_verifier / "
                    "_build_client_id / _build_oauth_url in login.py and update "
                    "amazon_setup._build_login_url accordingly."
                ) from exc

            verifier_str = (
                code_verifier.decode() if isinstance(code_verifier, bytes) else str(code_verifier)
            )
            return verifier_str, str(url)

    # ================================================================== #
    # >>> LIBRARY INTEGRATION POINT 2: register device from auth code     #
    # ================================================================== #
    async def _register_device(
        self,
        authorization_code: str,
        code_verifier: str,
        domain: str,
    ) -> dict[str, Any]:
        """Exchange the authorization code for device tokens (login_data dict).

        VERIFY ON PI: as researched, login.py's _register_device(data) takes a
        dict with 'authorization_code' and 'code_verifier' and returns/saves a
        login_data dict containing: adp_token, device_private_key, access_token,
        refresh_token, expires, website_cookies, store_authentication_cookie,
        device_info, customer_info, site. Adapt the call below if the pinned
        version's signature differs.
        """
        try:
            import aiohttp
            from aioamazondevices.api import AmazonEchoApi  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise AmazonSetupError("aioamazondevices is not installed.") from exc

        async with aiohttp.ClientSession() as session:
            api = AmazonEchoApi(session, "", "", login_data={"site": f"https://www.amazon.{domain}"})
            try:
                login_data = await api._register_device(  # type: ignore[attr-defined]
                    {
                        "authorization_code": authorization_code,
                        "code_verifier": code_verifier,
                    }
                )
            except AttributeError as exc:
                raise AmazonSetupError(
                    "The installed aioamazondevices version does not expose "
                    "_register_device as expected. Verify login.py and update "
                    "amazon_setup._register_device accordingly."
                ) from exc
            except Exception as exc:
                raise AmazonSetupError(f"Device registration failed: {exc}") from exc

            if not isinstance(login_data, dict):
                raise AmazonSetupError(
                    "Registration returned an unexpected result; expected a "
                    "login-data dict."
                )
            login_data.setdefault("site", f"https://www.amazon.{domain}")
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
