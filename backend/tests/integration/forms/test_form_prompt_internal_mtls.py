"""End-to-end mTLS tests for the internal form prompt create and batch routes.

These run the real forms router behind a real HTTPS server: the TLS handshake,
``TLSH11Protocol`` (which puts the verified peer cert into the ASGI scope),
``ClientCertAuthMiddleware``, ``require_internal_service`` and
``get_current_user``. Only the database-backed ``FormPromptService`` is stubbed,
so the test can check which identity the route would have run as.
"""

from __future__ import annotations

import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import Depends, FastAPI

from syntara.auth import get_current_user
from syntara.auth.cert_middleware import ClientCertAuthMiddleware
from syntara.auth.services.token_service import TokenService
from syntara.authz.exceptions import (
    AuthorizationDeniedError,
    InternalServiceRequiredError,
    authorization_denied_handler,
    internal_service_required_handler,
)
from syntara.core.database.session import get_db
from syntara.core.models import User  # noqa: TC001 - FastAPI resolves the Depends annotation at runtime
from syntara.core.models.principal import service_principal_id
from syntara.core.tls.protocol import TLSH11Protocol
from syntara.forms.models.api_models import (
    BatchFormPromptRequest,
    BatchUpdateResponse,
    BatchUpdateResult,
    FormPromptCreateRequest,
    FormPromptStatus,
    FormPromptSummary,
)
from syntara.forms.router import get_form_prompt_service
from syntara.forms.router import router as forms_router
from tests.fixtures.tls import generate_ca, generate_service_cert

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator
    from contextlib import AbstractContextManager
    from pathlib import Path

pytestmark = [pytest.mark.integration]

_WORKER_CN = "worker.ao.svc"
_FORM_PROMPTS_PATH = "/api/v1/form_prompts"
_CREATE_PAYLOAD = {
    "execution_id": str(uuid4()),
    "project_id": str(uuid4()),
    "prompt_node_id": "form1",
    "name": "mTLS form",
    "temporal_activity_id": "form1",
    "form_definition": {"fields": [{"value_name": "reason", "type": "text", "label": "Reason", "required": False}]},
}
_BATCH_PAYLOAD = {"updates": [{"prompt_id": str(uuid4()), "status": "expired"}]}
_ROUTES = [
    pytest.param("", _CREATE_PAYLOAD, 201, id="create"),
    pytest.param("/batch", _BATCH_PAYLOAD, 200, id="batch"),
]


@dataclass
class _RecordingService:
    """Stands in for FormPromptService and records the identity each call ran as."""

    users: list[User] = field(default_factory=list)
    current_user: User | None = None

    async def create(self, request: FormPromptCreateRequest) -> FormPromptSummary:
        assert self.current_user is not None
        self.users.append(self.current_user)
        return FormPromptSummary(
            id=uuid4(),
            execution_id=request.execution_id,
            project_id=request.project_id,
            prompt_node_id=request.prompt_node_id,
            name=request.name,
            status=FormPromptStatus.PENDING,
            temporal_activity_id=request.temporal_activity_id,
        )

    async def batch_update_status(self, request: BatchFormPromptRequest) -> BatchUpdateResponse:
        assert self.current_user is not None
        self.users.append(self.current_user)
        results = [BatchUpdateResult(prompt_id=str(u.prompt_id), success=True) for u in request.updates]
        return BatchUpdateResponse(results=results, total_success=len(results), total_failed=0)


@pytest.fixture(scope="module")
def certs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """CA, server cert and an allowlisted worker cert."""
    certs_dir = tmp_path_factory.mktemp("form_prompt_mtls")
    ca_key, ca_cert = generate_ca(certs_dir)
    server_cert, server_key = generate_service_cert(
        certs_dir, ca_key, ca_cert, common_name="backend.ao.svc", filename="server"
    )
    worker_cert, worker_key = generate_service_cert(
        certs_dir, ca_key, ca_cert, common_name=_WORKER_CN, filename="worker"
    )
    return {
        "ca": certs_dir / "ca.pem",
        "server_cert": server_cert,
        "server_key": server_key,
        "worker_cert": worker_cert,
        "worker_key": worker_key,
    }


@pytest.fixture
def service() -> _RecordingService:
    return _RecordingService()


@pytest.fixture
def server(
    certs: dict[str, Path],
    service: _RecordingService,
    override_settings: Callable[..., AbstractContextManager[object]],
) -> Generator[str, None, None]:
    """Serve the forms router over HTTPS with the production TLS protocol and cert middleware."""
    app = FastAPI()
    # Register directly: some unit tests clear the global exception registry used by register_exceptions().
    app.add_exception_handler(AuthorizationDeniedError, authorization_denied_handler)  # type: ignore[arg-type]
    app.add_exception_handler(InternalServiceRequiredError, internal_service_required_handler)  # type: ignore[arg-type]
    app.include_router(forms_router, prefix="/api/v1")

    async def no_db() -> AsyncGenerator[None, None]:
        # The cert path in get_current_user never touches the database.
        yield None

    def recording_service(user: Annotated[User, Depends(get_current_user)]) -> _RecordingService:
        service.current_user = user
        return service

    app.dependency_overrides[get_db] = no_db
    app.dependency_overrides[get_form_prompt_service] = recording_service

    with override_settings(s2s_tls_enabled=True, s2s_tls_cn_allowlist=[_WORKER_CN], s2s_tls_crl_path=None):
        config = uvicorn.Config(
            ClientCertAuthMiddleware(app),
            host="127.0.0.1",
            port=0,
            log_level="warning",
            ssl_certfile=str(certs["server_cert"]),
            ssl_keyfile=str(certs["server_key"]),
            ssl_ca_certs=str(certs["ca"]),
            ssl_cert_reqs=ssl.CERT_OPTIONAL,
            http=TLSH11Protocol,
        )
        uv_server = uvicorn.Server(config)
        thread = threading.Thread(target=uv_server.run, daemon=True)
        thread.start()
        try:
            for _ in range(200):
                if uv_server.started:
                    break
                time.sleep(0.05)
            else:
                msg = "form prompt mTLS test server did not start within 10s"
                raise TimeoutError(msg)
            port = uv_server.servers[0].sockets[0].getsockname()[1]
            yield f"https://127.0.0.1:{port}"
        finally:
            uv_server.should_exit = True
            thread.join(timeout=5)


def _client(certs: dict[str, Path], identity: str | None) -> httpx.Client:
    ctx = ssl.create_default_context(cafile=str(certs["ca"]))
    if identity is not None:
        ctx.load_cert_chain(certfile=str(certs[f"{identity}_cert"]), keyfile=str(certs[f"{identity}_key"]))
    return httpx.Client(verify=ctx)


def _user_token() -> str:
    """A valid, signed user access token, so rejection can't be blamed on a bad token."""
    return TokenService().create_access_token(subject_id=uuid4(), username="alice", email="alice@example.com")


@pytest.mark.parametrize(("suffix", "payload", "success_status"), _ROUTES)
def test_worker_cert_runs_as_service_principal(
    server: str,
    certs: dict[str, Path],
    service: _RecordingService,
    suffix: str,
    payload: dict[str, object],
    success_status: int,
) -> None:
    with _client(certs, "worker") as client:
        response = client.post(f"{server}{_FORM_PROMPTS_PATH}{suffix}", json=payload)

    assert response.status_code == success_status, response.text
    assert len(service.users) == 1
    assert service.users[0].username == _WORKER_CN
    assert service.users[0].id == service_principal_id(_WORKER_CN)


@pytest.mark.parametrize(("suffix", "payload", "success_status"), _ROUTES)
def test_worker_cert_with_user_bearer_token_is_rejected(
    server: str,
    certs: dict[str, Path],
    service: _RecordingService,
    suffix: str,
    payload: dict[str, object],
    success_status: int,
) -> None:
    with _client(certs, "worker") as client:
        response = client.post(
            f"{server}{_FORM_PROMPTS_PATH}{suffix}",
            json=payload,
            headers={"Authorization": f"Bearer {_user_token()}"},
        )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "AUTHORIZATION_DENIED"
    assert service.users == []


@pytest.mark.parametrize(("suffix", "payload", "success_status"), _ROUTES)
def test_user_bearer_token_without_cert_is_rejected(
    server: str,
    certs: dict[str, Path],
    service: _RecordingService,
    suffix: str,
    payload: dict[str, object],
    success_status: int,
) -> None:
    with _client(certs, None) as client:
        response = client.post(
            f"{server}{_FORM_PROMPTS_PATH}{suffix}",
            json=payload,
            headers={"Authorization": f"Bearer {_user_token()}"},
        )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "AUTHORIZATION_DENIED"
    assert service.users == []
