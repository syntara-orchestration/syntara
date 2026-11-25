"""Fixtures for the live AO+EP hello-world e2e (backend suite, local demo stack).

Runs with the rest of the backend e2e suite. The AO half uses the same
direct-httpx client as before; the Execution Plane half (the proof that the
script ran on EP, not in Temporal) activates only when EP_API_URL is set —
otherwise the test skips, like other optional-infrastructure e2e tests.
"""

from __future__ import annotations

import logging
import os
import ssl
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

LOGGER = logging.getLogger(__name__)

_TERMINAL_FAILURE_STATUSES = frozenset({"failed", "cancelled", "completed_with_errors"})
_DEFAULT_POLL_TIMEOUT_SECONDS = 180.0
_DEFAULT_POLL_INTERVAL_SECONDS = 3.0
_EP_JWT_AUDIENCE = "execution-plane"
_EP_JWT_CLIENT_ID = "syntara-orchestration"
_EP_JWT_ISSUER = "http://localhost:8000"
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _optional_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


class AoClient:
    """Talk to a live Automation Orchestrator API with a self-signed cert."""

    def __init__(self, base_url: str, password: str) -> None:
        """Authenticate against AO and keep a shared HTTP client."""
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/api/v1"
        # Kind/Konflux AO serves a self-signed ingress certificate.
        self._client = httpx.Client(verify=False, timeout=30.0)  # noqa: S501
        self._token = self._login(password)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _json(self, response: httpx.Response) -> object:
        if response.status_code >= 400:
            pytest.fail(f"{response.request.method} {response.request.url} -> {response.status_code}: {response.text}")
        if not response.content:
            return None
        return response.json()

    def _login(self, password: str) -> str:
        username = os.environ.get("ADMIN_USERNAME", "admin")
        response = self._client.post(
            f"{self.api}/auth/login",
            json={"username": username, "password": password},
        )
        body = self._json(response)
        token = body.get("access_token") if isinstance(body, dict) else None
        if not token:
            pytest.fail(f"AO login failed at {self.api}/auth/login")
        return str(token)

    def list_projects(self) -> list[dict[str, Any]]:
        body = self._json(self._client.get(f"{self.api}/projects", headers=self._headers()))
        resources = body.get("resources") if isinstance(body, dict) else None
        if not isinstance(resources, list):
            pytest.fail(f"unexpected projects payload: {body!r}")
        return [item for item in resources if isinstance(item, dict)]

    def default_project_id(self) -> str:
        projects = self.list_projects()
        default = next((item for item in projects if item.get("is_default") is True), None)
        chosen = default or (projects[0] if projects else None)
        project_id = chosen.get("id") if chosen else None
        if not project_id:
            pytest.fail("no AO project found; the Kind stack must be seeded")
        return str(project_id)

    def create_workflow(self, body: dict[str, Any]) -> dict[str, Any]:
        created = self._json(
            self._client.post(
                f"{self.api}/workflows",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=body,
            )
        )
        if not isinstance(created, dict) or not created.get("id"):
            pytest.fail(f"failed to create workflow: {created!r}")
        return created

    def create_execution(self, workflow_id: str, trigger_node_id: str = "trigger") -> dict[str, Any]:
        created = self._json(
            self._client.post(
                f"{self.api}/executions",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"workflow_id": workflow_id, "trigger_node_id": trigger_node_id, "input_data": {}},
            )
        )
        if not isinstance(created, dict) or not created.get("id"):
            pytest.fail(f"failed to create execution: {created!r}")
        return created

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        body = self._json(
            self._client.get(
                f"{self.api}/executions/{execution_id}",
                headers=self._headers(),
                params={"include": "activities"},
            )
        )
        if not isinstance(body, dict):
            pytest.fail(f"unexpected execution payload: {body!r}")
        return body

    def poll_execution(self, execution_id: str) -> dict[str, Any]:
        timeout_seconds = float(os.environ.get("E2E_POLL_TIMEOUT", _DEFAULT_POLL_TIMEOUT_SECONDS))
        interval_seconds = float(os.environ.get("E2E_POLL_INTERVAL", _DEFAULT_POLL_INTERVAL_SECONDS))
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self.get_execution(execution_id)
            status = str(last.get("status") or "")
            LOGGER.info("execution %s status=%s", execution_id, status)
            if status == "completed":
                return last
            if status in _TERMINAL_FAILURE_STATUSES:
                pytest.fail(
                    f"execution {execution_id} ended with status={status}; error_details={last.get('error_details')!r}"
                )
            time.sleep(interval_seconds)
        pytest.fail(
            f"execution {execution_id} did not finish after {timeout_seconds:.0f}s; "
            f"last status={last.get('status')!r} error_details={last.get('error_details')!r}"
        )

    def list_activities(self, execution_id: str) -> list[dict[str, Any]]:
        body = self._json(self._client.get(f"{self.api}/executions/{execution_id}/activities", headers=self._headers()))
        resources = body.get("resources") if isinstance(body, dict) else None
        if not isinstance(resources, list):
            pytest.fail(f"unexpected activities payload: {body!r}")
        return [item for item in resources if isinstance(item, dict)]


class EpClient:
    """Talk to a live Execution Plane API with an AO-signed service JWT."""

    def __init__(self, base_url: str, token: str, ca_file: Path) -> None:
        """Keep a shared HTTPS client for work-item reads."""
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/v1"
        context = ssl.create_default_context(cafile=str(ca_file))
        self._client = httpx.Client(verify=context, timeout=30.0)
        self._token = token

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def _json(self, response: httpx.Response) -> object:
        if response.status_code >= 400:
            pytest.fail(f"{response.request.method} {response.request.url} -> {response.status_code}: {response.text}")
        if not response.content:
            return None
        return response.json()

    def get_work_item(self, work_item_id: str) -> dict[str, Any] | None:
        response = self._client.get(f"{self.api}/work-items/{work_item_id}", headers=self._headers())
        if response.status_code == 404:
            return None
        body = self._json(response)
        if not isinstance(body, dict):
            pytest.fail(f"unexpected work-item payload: {body!r}")
        return body

    def list_work_items(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"limit": limit, "sort": "-created_at"}
        if status:
            params["status"] = status
        body = self._json(self._client.get(f"{self.api}/work-items", headers=self._headers(), params=params))
        resources = body.get("resources") if isinstance(body, dict) else None
        if not isinstance(resources, list):
            pytest.fail(f"unexpected work-item list payload: {body!r}")
        return [item for item in resources if isinstance(item, dict)]


def _mint_ep_service_token() -> str:
    explicit = os.environ.get("EP_SERVICE_TOKEN")
    if explicit:
        return explicit
    try:
        import jwt
    except ImportError:
        pytest.fail("EP_SERVICE_TOKEN or PyJWT is required to query the Execution Plane")
    key_path = Path(os.environ.get("EP_AO_JWT_PRIVATE_KEY_FILE") or _BACKEND_ROOT / ".secrets" / "jwt-primary.pem")
    if not key_path.is_file():
        pytest.fail(f"AO JWT private key not found at {key_path}; set EP_AO_JWT_PRIVATE_KEY_FILE or EP_SERVICE_TOKEN")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": os.environ.get("EP_AO_JWT_ISSUER", _EP_JWT_ISSUER),
            "aud": os.environ.get("EP_SERVICE_JWT_AUDIENCE", _EP_JWT_AUDIENCE),
            "client_id": os.environ.get("EP_AO_CLIENT_ID", _EP_JWT_CLIENT_ID),
            "scope": "work-items:read",
            "all_projects": True,
            "iat": now,
            "exp": now + timedelta(hours=8),
        },
        key_path.read_text(encoding="utf-8"),
        algorithm="ES256",
    )
    if not token:
        pytest.fail("Failed to mint an AO service token for the Execution Plane")
    return token


@pytest.fixture(scope="session")
def ao_base_url() -> str:
    url = _optional_env("AO_API_BASE", "BASE", "APP_BASE_URL")
    if not url:
        pytest.skip("AO_API_BASE, BASE, or APP_BASE_URL must be set for live e2e tests")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def ao_admin_password() -> str:
    password = _optional_env("ADMIN_PASSWORD", "APP_ADMIN_PASSWORD")
    if password:
        return password
    path = os.environ.get("APP_ADMIN_PASSWORD_PATH")
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()
    pytest.skip("ADMIN_PASSWORD or APP_ADMIN_PASSWORD_PATH must be set for live e2e tests")


@pytest.fixture(scope="session")
def ao_client(ao_base_url: str, ao_admin_password: str) -> Iterator[AoClient]:
    client = AoClient(ao_base_url, ao_admin_password)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def ep_base_url() -> str:
    url = _optional_env("EP_API_URL")
    if not url:
        pytest.skip(
            "EP_API_URL is not set; skipping the Execution Plane proof "
            "(set it, plus EP_API_CA_FILE / EP_SERVICE_TOKEN or EP_AO_JWT_PRIVATE_KEY_FILE, "
            "against a deployment with an Execution Plane to activate it)"
        )
    return url.rstrip("/")


@pytest.fixture(scope="session")
def ep_client(ep_base_url: str) -> Iterator[EpClient]:
    ca_env = os.environ.get("EP_API_CA_FILE")
    ca_file = Path(ca_env) if ca_env else _BACKEND_ROOT / ".secrets" / "certs" / "ca.pem"
    if not ca_file.is_file():
        pytest.fail(f"EP API CA not found at {ca_file}; set EP_API_CA_FILE")
    client = EpClient(ep_base_url, _mint_ep_service_token(), ca_file)
    try:
        yield client
    finally:
        client.close()
