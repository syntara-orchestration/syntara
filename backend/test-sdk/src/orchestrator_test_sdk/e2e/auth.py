"""Authentication helpers for Syntara E2E tests.

Provides session management, CSRF utilities, token refresh, and request-ID
correlation helpers used across E2E and auth-specific test suites.
"""

from __future__ import annotations

import os
import time
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import httpx
from syntara_api_client import AuthenticatedClient, Client
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.api.authentication.get_csrf_token import sync_detailed as csrf_token_sync
from syntara_api_client.api.authentication.get_current_user import sync_detailed as get_user_sync
from syntara_api_client.api.authentication.login import sync_detailed as login_sync
from syntara_api_client.api.authentication.refresh_token import sync_detailed as refresh_sync
from syntara_api_client.models.access_token_response import AccessTokenResponse
from syntara_api_client.models.csrf_token_response import CsrfTokenResponse
from syntara_api_client.models.login_request import LoginRequest

from orchestrator_test_sdk.e2e.tls import e2e_ssl_context

if TYPE_CHECKING:
    from collections.abc import Generator

    from syntara_api_client.models.error_data import ErrorData
    from syntara_api_client.models.user_info import UserInfo
    from syntara_api_client.types import Response

# ---------------------------------------------------------------------------
# Cookie / header name constants
# ---------------------------------------------------------------------------

REFRESH_COOKIE_NAME = "ao_refresh_token"
CSRF_COOKIE_NAME = "ao_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"

# ---------------------------------------------------------------------------
# Token refresh timing constants
# ---------------------------------------------------------------------------

_TOKEN_REFRESH_INTERVAL = 300  # Re-authenticate after 5 minutes (token lifetime is 15 min)
_REVOCATION_TTL_BUFFER = 15.0  # Slightly longer than server's _CACHE_TTL (10 s)

# ---------------------------------------------------------------------------
# Request-ID correlation header
# ---------------------------------------------------------------------------

REQUEST_ID_HEADER = "X-Request-Id"

# ---------------------------------------------------------------------------
# TLS / secrets helpers
# ---------------------------------------------------------------------------


def admin_password() -> str:
    """Return the built-in admin password from the configured secrets file."""
    password_path = Path(os.environ.get("APP_ADMIN_PASSWORD_PATH", ".secrets/admin-password"))
    if not password_path.exists():
        msg = f"Admin password file not found: {password_path}. Run 'make secrets-generate'."
        raise RuntimeError(msg)

    password = password_path.read_text().strip()
    if not password:
        msg = f"Admin password file is empty: {password_path}"
        raise RuntimeError(msg)

    return password


# ---------------------------------------------------------------------------
# Session / CSRF helpers
# ---------------------------------------------------------------------------


def _require_session_cookies(cookies: dict[str, str]) -> None:
    missing = [name for name in (REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME) if name not in cookies]
    if missing:
        msg = f"Session cookies missing required keys: {', '.join(missing)}"
        raise RuntimeError(msg)


_TRANSIENT_STATUS_CODES = {HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.GATEWAY_TIMEOUT}
_LOGIN_RETRIES = 6
_LOGIN_RETRY_DELAY = 5.0


def local_login_session(
    base_url: str,
    username: str,
    password: str,
) -> tuple[str, dict[str, str]]:
    """Log in via POST /auth/login and return (access_token, refresh cookies).

    Retries on transient 502/503/504 responses that occur when the backend is
    temporarily unavailable (e.g. recovering from resource pressure after a
    large E2E suite).
    """
    last_response: httpx.Response | None = None
    for _attempt in range(_LOGIN_RETRIES):
        response = httpx.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
            verify=e2e_ssl_context(),
            timeout=30,
        )
        if response.status_code == HTTPStatus.OK:
            access_token: str = response.json()["access_token"]
            cookies = dict(response.cookies)
            _require_session_cookies(cookies)
            return access_token, cookies
        last_response = response
        if response.status_code not in _TRANSIENT_STATUS_CODES:
            break
        time.sleep(_LOGIN_RETRY_DELAY)

    msg = f"Login failed for {username}: {last_response.status_code} {last_response.text!r}"  # type: ignore[union-attr]
    raise RuntimeError(msg)


def _csrf_headers_from_client(client: Client) -> dict[str, str]:
    csrf_resp = csrf_token_sync(client=client)
    if csrf_resp.status_code != HTTPStatus.OK or not isinstance(csrf_resp.parsed, CsrfTokenResponse):
        msg = f"CSRF token fetch failed: {csrf_resp.status_code} {csrf_resp.content!r}"
        raise RuntimeError(msg)
    csrf_token_response = cast("CsrfTokenResponse", csrf_resp.assert_and_get())
    return {CSRF_HEADER_NAME: csrf_token_response.csrf_token}


def csrf_headers_for_cookies(base_url: str, cookies: dict[str, str]) -> dict[str, str]:
    """Return X-CSRF-Token header derived from the session CSRF cookie."""
    _require_session_cookies(cookies)
    client = Client(base_url=f"{base_url}/api/v1", cookies=cookies, verify_ssl=e2e_ssl_context())
    return _csrf_headers_from_client(client)


def client_with_csrf_cookies(base_url: str, cookies: dict[str, str]) -> Client:
    """Return an API client with session cookies and X-CSRF-Token for cookie-auth endpoints."""
    _require_session_cookies(cookies)
    client = Client(base_url=f"{base_url}/api/v1", cookies=cookies, verify_ssl=e2e_ssl_context())
    return client.with_headers(_csrf_headers_from_client(client))


def refresh_with_cookies(
    base_url: str,
    cookies: dict[str, str],
) -> Response[AccessTokenResponse | Any | ErrorData]:
    """Call POST /auth/refresh using refresh and CSRF cookies plus X-CSRF-Token."""
    return refresh_sync(client=client_with_csrf_cookies(base_url, cookies))


def logout_with_session(
    base_url: str,
    access_token: str,
    cookies: dict[str, str],
) -> httpx.Response:
    """Call POST /auth/logout with Bearer token, session cookies, and X-CSRF-Token."""
    headers = {"Authorization": f"Bearer {access_token}", **csrf_headers_for_cookies(base_url, cookies)}
    return httpx.post(
        f"{base_url}/api/v1/auth/logout",
        headers=headers,
        cookies=cookies,
        verify=e2e_ssl_context(),
        timeout=30,
    )


def get_current_user_with_token(
    base_url: str,
    access_token: str,
) -> Response[Any | ErrorData | UserInfo]:
    """Call GET /auth/me with a Bearer access token."""
    client = AuthenticatedClient(base_url=f"{base_url}/api/v1", token=access_token, verify_ssl=e2e_ssl_context())
    return get_user_sync(client=client)


def assert_refresh_succeeds(base_url: str, cookies: dict[str, str]) -> AccessTokenResponse:
    """Refresh must return 200 with an access token."""
    resp = refresh_with_cookies(base_url, cookies)
    assert resp.status_code == HTTPStatus.OK, f"Expected refresh 200, got {resp.status_code}: {resp.content!r}"
    assert isinstance(resp.parsed, AccessTokenResponse)
    return resp.parsed


def assert_refresh_unauthorized(base_url: str, cookies: dict[str, str]) -> None:
    """Refresh must return 401 when the session is revoked."""
    resp = refresh_with_cookies(base_url, cookies)
    assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
        f"Expected refresh 401, got {resp.status_code}: {resp.content!r}"
    )


def logout_response_body(response: httpx.Response) -> dict[str, Any]:
    """Parse logout JSON body."""
    assert response.status_code == HTTPStatus.OK, f"Expected logout 200, got {response.status_code}: {response.text!r}"
    body: dict[str, Any] = response.json()
    assert body.get("detail") == "Successfully logged out"
    return body


# ---------------------------------------------------------------------------
# Auto-refresh auth
# ---------------------------------------------------------------------------


def _is_globally_revoked(response: httpx.Response) -> bool:
    """Return True when the response is a TOKEN_GLOBALLY_REVOKED 401."""
    try:
        return bool(response.json().get("code") == "TOKEN_GLOBALLY_REVOKED")
    except Exception:
        return False


class _AutoRefreshAuth(httpx.Auth):
    """httpx Auth that proactively and reactively refreshes expired JWT tokens.

    Proactive: re-authenticates when the token age exceeds _TOKEN_REFRESH_INTERVAL.
    Reactive: retries with a fresh token on any 401 response.
      - TOKEN_GLOBALLY_REVOKED: loops until the revocation TTL window (~10 s) expires,
        because freshly-issued tokens are also rejected until the cache clears.
      - Any other 401: retries exactly once (unchanged legacy behaviour).
    """

    def __init__(
        self,
        base_url: str,
        initial_token: str,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._base_url = base_url
        self.token = initial_token
        self._last_refresh = time.monotonic()
        self._username = username
        self._password = password

    def _refresh(self) -> None:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                if self._username and self._password:
                    self.token = _login(self._base_url, self._username, self._password)
                else:
                    self.token = _generate_e2e_token(self._base_url)
                self._last_refresh = time.monotonic()
            except RuntimeError as exc:
                last_exc = exc
                time.sleep(2 * (attempt + 1))
            else:
                return
        raise last_exc  # type: ignore[misc]

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        if time.monotonic() - self._last_refresh > _TOKEN_REFRESH_INTERVAL:
            self._refresh()
        request.headers["Authorization"] = f"Bearer {self.token}"
        response = yield request
        if response.status_code == 401:
            deadline = time.monotonic() + _REVOCATION_TTL_BUFFER
            while True:
                self._refresh()
                request.headers["Authorization"] = f"Bearer {self.token}"
                response = yield request
                if response.status_code != 401 or not _is_globally_revoked(response) or time.monotonic() >= deadline:
                    break
                time.sleep(0.5)


# ---------------------------------------------------------------------------
# Login / client helpers
# ---------------------------------------------------------------------------


def _login(base_url: str, username: str, password: str) -> str:
    """Obtain a JWT access token via the generated login endpoint.

    Retries on transient 502/503/504 responses that occur when the backend is
    temporarily unavailable (e.g. recovering from resource pressure after a
    large E2E suite).
    """
    unauthenticated = Client(base_url=f"{base_url}/api/v1", verify_ssl=e2e_ssl_context())
    last_resp: Response[Any] | None = None
    for _attempt in range(_LOGIN_RETRIES):
        resp = login_sync(client=unauthenticated, body=LoginRequest(username=username, password=password))
        if resp.status_code == HTTPStatus.OK and isinstance(resp.parsed, AccessTokenResponse):
            return cast("AccessTokenResponse", resp.assert_and_get()).access_token
        last_resp = resp
        if resp.status_code not in _TRANSIENT_STATUS_CODES:
            break
        time.sleep(_LOGIN_RETRY_DELAY)

    msg = f"Login failed for {username}: {last_resp.status_code} {last_resp.content!r}"  # type: ignore[union-attr]
    raise RuntimeError(msg)


def _make_client(base_url: str, token: str) -> AuthenticatedClient:
    """Create an authenticated API client for the given base URL and token."""
    return AuthenticatedClient(
        base_url=f"{base_url}/api/v1",
        token=token,
        verify_ssl=e2e_ssl_context(),
        timeout=httpx.Timeout(60.0),
    )


def api_for(base_url: str, username: str, password: str) -> SyntaraApiRegistry:
    """Return a ``SyntaraApiRegistry`` authenticated as the given user."""
    token = _login(base_url, username, password)
    return SyntaraApiRegistry(_make_client(base_url, token))


def _generate_e2e_token(base_url: str) -> str:
    """Obtain a JWT access token for e2e tests via POST /auth/login."""
    password = admin_password()
    return _login(base_url, "admin", password)


def local_user_login(
    base_url: str,
    *,
    username: str | None = None,
    password: str | None = None,
) -> Response[Any]:
    """Login local user in Unauthenticated client. By default, login built-in admin."""
    resolved_username = username or "admin"
    resolved_password = password or admin_password()
    unauthenticated = Client(base_url=f"{base_url}/api/v1", verify_ssl=e2e_ssl_context())
    return login_sync(client=unauthenticated, body=LoginRequest(username=resolved_username, password=resolved_password))


# ---------------------------------------------------------------------------
# Request-ID correlation helpers (from tests/e2e/auth/conftest.py)
# ---------------------------------------------------------------------------


def new_request_id() -> str:
    """Generate a UUID request_id for X-Request-Id correlation."""
    return str(uuid4())


def client_with_request_id(client: Client, request_id: str) -> Client:
    """Return a client that sends the given X-Request-Id header."""
    return client.with_headers({REQUEST_ID_HEADER: request_id})


def api_with_request_id(api: SyntaraApiRegistry, request_id: str) -> SyntaraApiRegistry:
    """Return an API registry whose client sends the given X-Request-Id header."""
    return SyntaraApiRegistry(api._client.with_headers({REQUEST_ID_HEADER: request_id}))  # noqa: SLF001


def login_with_request_id(
    client: Client,
    *,
    username: str,
    password: str,
    request_id: str,
) -> Response[AccessTokenResponse | Any | ErrorData]:
    """Perform login with a correlated X-Request-Id header."""
    return login_sync(
        client=client_with_request_id(client, request_id),
        body=LoginRequest(username=username, password=password),
    )
