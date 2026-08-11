"""Live deployment fixtures for E2E and performance tests."""

from __future__ import annotations

import logging
import os
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

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0

_RETRYABLE_EXCEPTIONS = (
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.WriteError,
    ConnectionResetError,
)


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, _RETRYABLE_EXCEPTIONS)


def _generate_live_token(base_url: str) -> str:
    """Obtain a JWT access token for tests that hit a live Nexus deployment.

    Resolution order:
    1. NEXUS_API_TOKEN env var (pre-generated token for remote deployments)
    2. POST /auth/login using admin password from APP_ADMIN_PASSWORD_PATH

    Retries transient connection errors with exponential backoff.
    """
    env_token = os.environ.get("NEXUS_API_TOKEN")
    if env_token:
        return env_token

    password_path = Path(os.environ.get("APP_ADMIN_PASSWORD_PATH", ".secrets/admin-password"))
    if not password_path.exists():
        msg = f"Admin password file not found: {password_path}. Set NEXUS_API_TOKEN or run 'make secrets-generate'."
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
def nexus_base_url() -> str:
    """Return the Nexus API base URL from the environment."""
    return os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def auth_headers(nexus_base_url: str) -> dict[str, str]:
    """Return Bearer auth headers for raw httpx calls."""
    token = _generate_live_token(nexus_base_url)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def nexus_client(nexus_base_url: str) -> AuthenticatedClient:
    """Return an authenticated Syntara API client for the target deployment."""
    from syntara_api_client import AuthenticatedClient

    ssl_ctx = e2e_ssl_context()
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = httpx.get(f"{nexus_base_url}/health", timeout=5, verify=ssl_ctx)
            response.raise_for_status()
            last_exc = None
            break
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_exc = exc
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
            f"Nexus deployment not available at {nexus_base_url}: {last_exc}\n"
            "Start the services first with: make services-run && make dev",
            returncode=1,
        )

    access_token = _generate_live_token(nexus_base_url)
    return AuthenticatedClient(
        base_url=f"{nexus_base_url}/api/v1",
        token=access_token,
        verify_ssl=ssl_ctx,
    )


@pytest.fixture(scope="session")
def syntara_api(nexus_base_url: str, nexus_client: AuthenticatedClient) -> SyntaraApiRegistry:
    """Return a SyntaraApiRegistry with internal_metrics wired to the root URL."""
    from syntara_api_client import AuthenticatedClient
    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.api.internal_metrics import InternalMetricsApi

    registry = SyntaraApiRegistry(nexus_client)

    root_client = AuthenticatedClient(
        base_url=nexus_base_url,
        token=nexus_client.token,
        verify_ssl=e2e_ssl_context(),
    )
    registry.__dict__["internal_metrics"] = InternalMetricsApi(client=root_client)

    return registry
