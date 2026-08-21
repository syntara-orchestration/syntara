"""Shared helpers for service account E2E tests."""

from __future__ import annotations

import base64
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import _retry_api_call
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context
from syntara_api_client import Client
from syntara_api_client.models.body_token import BodyToken
from syntara_api_client.models.service_account_create import ServiceAccountCreate
from syntara_api_client.models.service_account_credential_create import ServiceAccountCredentialCreate
from syntara_api_client.models.service_account_credential_type import ServiceAccountCredentialType

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry


def create_sa(api: SyntaraApiRegistry, project_id: UUID, prefix: str = "e2e-sa", **overrides: Any) -> Any:  # noqa: ANN401
    """Create a service account and return the parsed response."""
    name = overrides.pop("name", unique_name(prefix))
    resp = api.service_accounts.create(
        body=ServiceAccountCreate(name=name, project_id=project_id, **overrides),
    )
    assert resp.status_code == HTTPStatus.CREATED, f"Expected 201, got {resp.status_code}: {resp.content!r}"
    return resp.assert_and_get()


def create_sa_with_credential(
    api: SyntaraApiRegistry,
    project_id: UUID,
) -> tuple[Any, str, str]:
    """Create a service account with a credential. Returns (sa, client_id, client_secret)."""
    sa = api.service_accounts.create(
        body=ServiceAccountCreate(name=unique_name("e2e-sa"), project_id=project_id),
    ).assert_and_get()

    cred = _retry_api_call(
        lambda: api.service_account_credentials.create(
            service_account_id=sa.id,
            body=ServiceAccountCredentialCreate(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS),
        )
    ).assert_and_get()

    return sa, cred.identifier, cred.client_secret


def unauth_client(base_url: str) -> Client:
    """Return an unauthenticated API client for token endpoint calls."""
    return Client(base_url=f"{base_url}/api/v1", verify_ssl=e2e_ssl_context())


def token_request(
    base_url: str,
    client_id: str,
    client_secret: str,
    *,
    grant_type: str = "client_credentials",
    use_basic_auth: bool = False,
) -> Any:  # noqa: ANN401
    """POST /auth/token via the generated client and return the Response."""
    body = BodyToken(grant_type=grant_type)

    if use_basic_auth:
        creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        client = unauth_client(base_url).with_headers({"Authorization": f"Basic {creds}"})
    else:
        body = BodyToken(grant_type=grant_type, client_id=client_id, client_secret=client_secret)
        client = unauth_client(base_url)

    from syntara_api_client.api.authentication.token import sync_detailed

    return sync_detailed(client=client, body=body)


CACHE_TTL_TIMEOUT = 12.0
POLL_INTERVAL = 0.5


def poll_until_status(
    base_url: str,
    access_token: str,
    expected: int | HTTPStatus,
    timeout: float = CACHE_TTL_TIMEOUT,
) -> httpx.Response:
    """Poll GET /auth/me until *expected* status code is seen, or timeout.

    The StaleTokenMiddleware has a 5s TTL cache, so after state changes
    (disable/delete/re-enable) we poll until the cached status expires.
    """
    deadline = time.monotonic() + timeout
    while True:
        resp = httpx.get(
            f"{base_url}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            verify=e2e_ssl_context(),
            timeout=10,
        )
        if resp.status_code == expected:
            return resp
        if time.monotonic() >= deadline:
            return resp
        time.sleep(POLL_INTERVAL)
