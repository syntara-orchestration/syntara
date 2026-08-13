"""Unit tests for project-scoped credential endpoints in projects/router.py."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from syntara.credentials.models.credential import (
    Credential,
    CredentialListResponse,
    CredentialRead,
    CredentialWorkflowRef,
)
from syntara.credentials.services.credential_service import CredentialService
from syntara.projects.router import router

PROJECT_ID = uuid4()
OTHER_PROJECT_ID = uuid4()
CREDENTIAL_ID = uuid4()
CRED_TYPE_ID = uuid4()


def _make_raw_cred(project_id=PROJECT_ID, credential_id=CREDENTIAL_ID) -> Credential:
    return Credential(
        id=credential_id,
        name="test-cred",
        credential_type_id=CRED_TYPE_ID,
        project_id=project_id,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


def _make_cred_read(project_id=PROJECT_ID, credential_id=CREDENTIAL_ID) -> CredentialRead:
    return CredentialRead(
        id=credential_id,
        name="test-cred",
        credential_type_id=CRED_TYPE_ID,
        inputs={"token": "$encrypted$"},
        enabled=True,
        project_id=project_id,
        workflow_count=0,
        created_by="admin",
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
        labels={},
    )


@pytest.fixture
def mock_credential_service() -> AsyncMock:
    """Mock CredentialService for dependency injection."""
    return AsyncMock(spec=CredentialService)


@pytest.fixture
def app(mock_credential_service: AsyncMock) -> FastAPI:
    """Create a test FastAPI app with project credential routes and mocked deps."""
    test_app = FastAPI()

    from syntara.auth import get_current_user
    from syntara.credentials.error_handlers import credential_not_found_handler
    from syntara.credentials.exceptions import CredentialNotFoundError
    from syntara.credentials.router import get_credential_service

    async def _no_auth() -> None:
        return None

    test_app.dependency_overrides[get_current_user] = lambda: MagicMock()
    test_app.dependency_overrides[get_credential_service] = lambda: mock_credential_service

    from syntara.projects import router as proj_mod

    for dep_name in [
        "_perm_credential_create",
        "_perm_credential_read",
        "_perm_credential_update",
        "_perm_credential_delete",
    ]:
        test_app.dependency_overrides[getattr(proj_mod, dep_name)] = _no_auth

    test_app.include_router(router, prefix="/api/v1")
    test_app.add_exception_handler(CredentialNotFoundError, credential_not_found_handler)  # type: ignore[arg-type]
    return test_app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create an async HTTP client for the test app."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestCreateProjectCredential:
    """Tests for POST /projects/{project_id}/credentials."""

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client: AsyncClient, mock_credential_service: AsyncMock) -> None:
        cred = _make_cred_read()
        mock_credential_service.create_credential.return_value = cred

        async with client:
            resp = await client.post(
                f"/api/v1/projects/{PROJECT_ID}/credentials",
                json={
                    "name": "test-cred",
                    "credential_type_id": str(CRED_TYPE_ID),
                    "inputs": {"token": "secret"},
                    "labels": {},
                },
            )

        assert resp.status_code == 201
        assert resp.json()["name"] == "test-cred"
        mock_credential_service.create_credential.assert_called_once()
        call_arg = mock_credential_service.create_credential.call_args[0][0]
        assert call_arg.project_id == PROJECT_ID


class TestListProjectCredentials:
    """Tests for GET /projects/{project_id}/credentials."""

    @pytest.mark.asyncio
    async def test_list_returns_200(self, client: AsyncClient, mock_credential_service: AsyncMock) -> None:
        mock_credential_service.list_credentials.return_value = CredentialListResponse(
            resources=[_make_cred_read()],
            next=None,
            prev=None,
        )

        async with client:
            resp = await client.get(f"/api/v1/projects/{PROJECT_ID}/credentials")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["resources"]) == 1

        call_kwargs = mock_credential_service.list_credentials.call_args[1]
        assert call_kwargs["allowed_projects"].project_ids == [PROJECT_ID]
        assert call_kwargs["allowed_projects"].all_projects is False


class TestGetProjectCredential:
    """Tests for GET /projects/{project_id}/credentials/{credential_id}."""

    @pytest.mark.asyncio
    async def test_get_returns_200(self, client: AsyncClient, mock_credential_service: AsyncMock) -> None:
        mock_credential_service.get_credential_raw.return_value = _make_raw_cred()
        mock_credential_service.get_credential.return_value = _make_cred_read()

        async with client:
            resp = await client.get(f"/api/v1/projects/{PROJECT_ID}/credentials/{CREDENTIAL_ID}")

        assert resp.status_code == 200
        assert resp.json()["id"] == str(CREDENTIAL_ID)
        mock_credential_service.get_credential_raw.assert_called_once_with(CREDENTIAL_ID)

    @pytest.mark.asyncio
    async def test_get_wrong_project_returns_404(self, client: AsyncClient, mock_credential_service: AsyncMock) -> None:
        mock_credential_service.get_credential_raw.return_value = _make_raw_cred(project_id=OTHER_PROJECT_ID)

        async with client:
            resp = await client.get(f"/api/v1/projects/{PROJECT_ID}/credentials/{CREDENTIAL_ID}")

        assert resp.status_code == 404
        mock_credential_service.get_credential.assert_not_called()


class TestUpdateProjectCredential:
    """Tests for PATCH /projects/{project_id}/credentials/{credential_id}."""

    @pytest.mark.asyncio
    async def test_patch_returns_200(self, client: AsyncClient, mock_credential_service: AsyncMock) -> None:
        mock_credential_service.get_credential_raw.return_value = _make_raw_cred()
        mock_credential_service.update_credential.return_value = _make_cred_read()

        async with client:
            resp = await client.patch(
                f"/api/v1/projects/{PROJECT_ID}/credentials/{CREDENTIAL_ID}",
                json={"name": "updated"},
            )

        assert resp.status_code == 200
        mock_credential_service.update_credential.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_wrong_project_returns_404(
        self, client: AsyncClient, mock_credential_service: AsyncMock
    ) -> None:
        mock_credential_service.get_credential_raw.return_value = _make_raw_cred(project_id=OTHER_PROJECT_ID)

        async with client:
            resp = await client.patch(
                f"/api/v1/projects/{PROJECT_ID}/credentials/{CREDENTIAL_ID}",
                json={"name": "updated"},
            )

        assert resp.status_code == 404
        mock_credential_service.update_credential.assert_not_called()


class TestDeleteProjectCredential:
    """Tests for DELETE /projects/{project_id}/credentials/{credential_id}."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(self, client: AsyncClient, mock_credential_service: AsyncMock) -> None:
        mock_credential_service.get_credential_raw.return_value = _make_raw_cred()

        async with client:
            resp = await client.delete(f"/api/v1/projects/{PROJECT_ID}/credentials/{CREDENTIAL_ID}")

        assert resp.status_code == 204
        mock_credential_service.delete_credential.assert_called_once_with(CREDENTIAL_ID)

    @pytest.mark.asyncio
    async def test_delete_wrong_project_returns_404(
        self, client: AsyncClient, mock_credential_service: AsyncMock
    ) -> None:
        mock_credential_service.get_credential_raw.return_value = _make_raw_cred(project_id=OTHER_PROJECT_ID)

        async with client:
            resp = await client.delete(f"/api/v1/projects/{PROJECT_ID}/credentials/{CREDENTIAL_ID}")

        assert resp.status_code == 404
        mock_credential_service.delete_credential.assert_not_called()


class TestGetProjectCredentialWorkflows:
    """Tests for GET /projects/{project_id}/credentials/{credential_id}/workflows."""

    @pytest.mark.asyncio
    async def test_get_workflows_returns_200(self, client: AsyncClient, mock_credential_service: AsyncMock) -> None:
        mock_credential_service.get_credential_raw.return_value = _make_raw_cred()
        mock_credential_service.get_credential_workflows.return_value = [
            CredentialWorkflowRef(id=uuid4(), name="wf-1"),
        ]

        async with client:
            resp = await client.get(f"/api/v1/projects/{PROJECT_ID}/credentials/{CREDENTIAL_ID}/workflows")

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "wf-1"

    @pytest.mark.asyncio
    async def test_get_workflows_wrong_project_returns_404(
        self, client: AsyncClient, mock_credential_service: AsyncMock
    ) -> None:
        mock_credential_service.get_credential_raw.return_value = _make_raw_cred(project_id=OTHER_PROJECT_ID)

        async with client:
            resp = await client.get(f"/api/v1/projects/{PROJECT_ID}/credentials/{CREDENTIAL_ID}/workflows")

        assert resp.status_code == 404
        mock_credential_service.get_credential_workflows.assert_not_called()
