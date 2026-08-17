"""Live deployment fixtures for E2E and performance tests."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

from orchestrator_test_sdk.e2e.tls import e2e_ssl_context

if TYPE_CHECKING:
    from syntara_api_client import AuthenticatedClient
    from syntara_api_client.api import SyntaraApiRegistry

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_BACKOFF_BASE = 1.0

_RETRYABLE_EXCEPTIONS = (
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.WriteError,
    httpx.ProxyError,
    ConnectionResetError,
)

_RETRYABLE_STATUS_CODES = frozenset({403, 502, 503, 504})


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, _RETRYABLE_EXCEPTIONS):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


class _TokenRefreshTransport(httpx.BaseTransport):
    """Wraps an httpx transport to auto-refresh the token on 401 responses.

    Thread-safe: uses a lock to ensure only one thread refreshes at a time.
    """

    def __init__(self, wrapped: httpx.BaseTransport, client_ref: AuthenticatedClient, base_url: str) -> None:
        self._wrapped = wrapped
        self._client_ref = client_ref
        self._base_url = base_url
        self._lock = threading.Lock()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._wrapped.handle_request(request)
        if response.status_code != 401:
            return response

        if "/auth/login" in str(request.url):
            return response

        response.read()
        response.close()

        with self._lock:
            current_auth = request.headers.get("Authorization", "")
            client_auth = self._client_ref.get_httpx_client().headers.get(self._client_ref.auth_header_name, "")
            if current_auth == client_auth:
                old_token = self._client_ref.token
                logger.info("Token expired, refreshing...")
                new_token = _generate_live_token(self._base_url)
                if new_token == old_token:
                    logger.warning(
                        "Token refresh returned the same token (likely a static NEXUS_API_TOKEN). "
                        "Cannot auto-refresh — returning 401 response."
                    )
                    return response
                self._client_ref.token = new_token
                new_header = f"{self._client_ref.prefix} {new_token}" if self._client_ref.prefix else new_token
                self._client_ref.get_httpx_client().headers[self._client_ref.auth_header_name] = new_header

        new_auth = self._client_ref.get_httpx_client().headers.get(self._client_ref.auth_header_name, "")
        request.headers[self._client_ref.auth_header_name] = new_auth
        return self._wrapped.handle_request(request)

    def close(self) -> None:
        self._wrapped.close()


def _generate_live_token(base_url: str) -> str:
    """Obtain a JWT access token for tests that hit a live Syntara deployment.

    Resolution order:
    1. SYNTARA_API_TOKEN env var (pre-generated token for remote deployments)
    2. POST /auth/login using admin password from APP_ADMIN_PASSWORD_PATH

    Retries transient connection errors with exponential backoff.
    """
    env_token = os.environ.get("SYNTARA_API_TOKEN")
    if env_token:
        return env_token

    password_path = Path(os.environ.get("APP_ADMIN_PASSWORD_PATH", ".secrets/admin-password"))
    if not password_path.exists():
        msg = f"Admin password file not found: {password_path}. Set SYNTARA_API_TOKEN or run 'make secrets-generate'."
        raise RuntimeError(msg)

    password = password_path.read_text().strip()
    if not password:
        msg = f"Admin password file is empty: {password_path}"
        raise RuntimeError(msg)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = httpx.post(
                f"{base_url}/api/v1/auth/login",
                json={"username": "admin", "password": password},
                verify=e2e_ssl_context(),
                timeout=10,
            )
            response.raise_for_status()
            token: str = response.json()["access_token"]
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
            if attempt < _MAX_RETRIES:
                backoff = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Login attempt %d/%d failed (%s: %s), retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    type(exc).__name__,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
        else:
            return token
    raise last_exc  # type: ignore[misc]


@pytest.fixture(scope="session")
def syntara_base_url() -> str:
    """Return the Syntara API base URL from the environment."""
    return os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def auth_headers(syntara_base_url: str) -> dict[str, str]:
    """Return Bearer auth headers for raw httpx calls."""
    token = _generate_live_token(syntara_base_url)
    return {"Authorization": f"Bearer {token}"}


def refresh_client_token(client: AuthenticatedClient, base_url: str) -> None:
    """Re-authenticate and update the client's token in-place.

    Useful for long-running test sessions where the JWT may expire between tests.
    """
    new_token = _generate_live_token(base_url)
    client.token = new_token
    httpx_client = client.get_httpx_client()
    httpx_client.headers[client.auth_header_name] = f"{client.prefix} {new_token}" if client.prefix else new_token


@pytest.fixture(scope="session")
def syntara_client(syntara_base_url: str) -> AuthenticatedClient:
    """Return an authenticated Syntara API client for the target deployment.

    Installs a transparent token-refresh transport that automatically
    re-authenticates on 401 responses, making long-running test sessions
    resilient to token expiry.
    """
    from syntara_api_client import AuthenticatedClient

    ssl_ctx = e2e_ssl_context()
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = httpx.get(f"{syntara_base_url}/health", timeout=5, verify=ssl_ctx)
            print(f"[syntara_client] health check attempt {attempt + 1}: {response.status_code}", flush=True)  # noqa: T201
            response.raise_for_status()
            last_exc = None
            break
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            print(f"[syntara_client] attempt {attempt + 1} failed: {type(exc).__name__}: {exc}", flush=True)  # noqa: T201
            if _is_retryable(exc) and attempt < _MAX_RETRIES:
                backoff = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Health check attempt %d/%d failed (%s: %s), retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    type(exc).__name__,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
            else:
                break

    if last_exc is not None:
        pytest.exit(
            f"Syntara deployment not available at {syntara_base_url}: {last_exc}\n"
            "Start the services first with: make services-run && make dev",
            returncode=1,
        )

    access_token = _generate_live_token(syntara_base_url)
    client = AuthenticatedClient(
        base_url=f"{syntara_base_url}/api/v1",
        token=access_token,
        verify_ssl=ssl_ctx,
    )

    httpx_client = client.get_httpx_client()
    original_transport = httpx_client._transport  # noqa: SLF001
    httpx_client._transport = _TokenRefreshTransport(original_transport, client, syntara_base_url)  # noqa: SLF001

    return client


@pytest.fixture(scope="session")
def syntara_api(syntara_base_url: str, syntara_client: AuthenticatedClient) -> SyntaraApiRegistry:
    """Return a SyntaraApiRegistry with internal_metrics wired to the root URL."""
    from syntara_api_client import AuthenticatedClient
    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.api.internal_metrics import InternalMetricsApi

    registry = SyntaraApiRegistry(syntara_client)

    root_client = AuthenticatedClient(
        base_url=syntara_base_url,
        token=syntara_client.token,
        verify_ssl=e2e_ssl_context(),
    )
    registry.__dict__["internal_metrics"] = InternalMetricsApi(client=root_client)

    return registry
