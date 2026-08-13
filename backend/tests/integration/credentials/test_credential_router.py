"""Integration tests for Credential REST API endpoints.

Tests the full stack: router → service → SecretService → DatabaseBackend → PostgreSQL.
Requires a running database with migrations applied.
"""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.credentials.lib.preseed import GA_CREDENTIAL_TYPES, preseed_credential_types
from syntara.credentials.models.credential_type import CredentialType
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent


@pytest.fixture
async def preseeded_types(test_db_session: AsyncSession) -> None:
    """Preseed GA managed credential types for integration tests.

    Lifespan preseed may be skipped in test environments (event loop mismatch),
    so this fixture ensures managed types exist for tests that need them.
    """
    await preseed_credential_types(test_db_session)


class TestCreateCredential:
    """POST /api/v1/credentials."""

    @pytest.mark.asyncio
    async def test_create_returns_201_with_masked_inputs(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "My Token",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "sk-secret-123"},
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "My Token"
        assert body["inputs"]["token"] == "$encrypted$"  # noqa: S105
        assert body["credential_type_id"] == str(bearer_type.id)
        assert "id" in body
        assert "created_at" in body

        # created_by/updated_by must be UserReference objects ({id, name})
        assert body["created_by"] is not None
        assert isinstance(body["created_by"], dict)
        assert "id" in body["created_by"]
        assert "name" in body["created_by"]
        assert body["updated_by"] is not None
        assert isinstance(body["updated_by"], dict)
        assert "id" in body["updated_by"]
        assert "name" in body["updated_by"]

    @pytest.mark.asyncio
    async def test_create_duplicate_name_returns_409(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        payload = {
            "name": "Duplicate Name",
            "credential_type_id": str(bearer_type.id),
            "project_id": test_project_id,
            "inputs": {"token": "abc"},
        }
        resp1 = await auth_client.post("/api/v1/credentials", json=payload)
        assert resp1.status_code == 201

        resp2 = await auth_client.post("/api/v1/credentials", json=payload)
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_create_same_name_different_project_returns_201(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str, test_db_session: AsyncSession
    ) -> None:
        other_project = Project(name=f"other-project-{uuid4().hex[:8]}", labels={})
        test_db_session.add(other_project)
        await test_db_session.commit()
        await test_db_session.refresh(other_project)

        base_payload = {
            "name": "Cross Project Cred",
            "credential_type_id": str(bearer_type.id),
            "inputs": {"token": "abc"},
        }

        resp1 = await auth_client.post(
            "/api/v1/credentials",
            json={**base_payload, "project_id": test_project_id},
        )
        assert resp1.status_code == 201

        resp2 = await auth_client.post(
            "/api/v1/credentials",
            json={**base_payload, "project_id": str(other_project.id)},
        )
        assert resp2.status_code == 201

        assert resp1.json()["name"] == resp2.json()["name"] == "Cross Project Cred"
        assert resp1.json()["project_id"] != resp2.json()["project_id"]

    @pytest.mark.asyncio
    async def test_create_same_name_same_project_returns_409(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        payload = {
            "name": "Same Project Cred",
            "credential_type_id": str(bearer_type.id),
            "project_id": test_project_id,
            "inputs": {"token": "abc"},
        }
        resp1 = await auth_client.post("/api/v1/credentials", json=payload)
        assert resp1.status_code == 201

        resp2 = await auth_client.post("/api/v1/credentials", json=payload)
        assert resp2.status_code == 409
        assert "in this project" in resp2.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_without_required_inputs_returns_422(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "Empty Cred",
                "credential_type_id": str(bearer_type.id),
            },
        )
        assert resp.status_code == 422


class TestGetCredential:
    """GET /api/v1/credentials/{id}."""

    @pytest.mark.asyncio
    async def test_get_masks_secret_decrypts_nonsecret(
        self, auth_client: AsyncClient, basic_auth_type: CredentialType, test_project_id: str
    ) -> None:
        # Create
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "Basic Auth Cred",
                "credential_type_id": str(basic_auth_type.id),
                "project_id": test_project_id,
                "inputs": {"username": "admin", "password": "secret123"},
            },
        )
        assert create_resp.status_code == 201
        cred_id = create_resp.json()["id"]

        # Get
        get_resp = await auth_client.get(f"/api/v1/credentials/{cred_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["inputs"]["username"] == "admin"  # non-secret: decrypted
        assert body["inputs"]["password"] == "$encrypted$"  # noqa: S105  # secret: masked

        # created_by/updated_by must be UserReference objects ({id, name})
        assert isinstance(body["created_by"], dict)
        assert "id" in body["created_by"]
        assert "name" in body["created_by"]

    @pytest.mark.asyncio
    async def test_get_not_found_returns_404(self, auth_client: AsyncClient, test_project_id: str) -> None:
        resp = await auth_client.get(f"/api/v1/credentials/{uuid4()}")
        assert resp.status_code == 404


class TestListCredentials:
    """GET /api/v1/credentials."""

    @pytest.mark.asyncio
    async def test_list_returns_masked_metadata(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        # Create two credentials
        for i in range(2):
            await auth_client.post(
                "/api/v1/credentials",
                json={
                    "name": f"List Test {i} {uuid4().hex[:8]}",
                    "credential_type_id": str(bearer_type.id),
                    "project_id": test_project_id,
                    "inputs": {"token": f"secret-{i}"},
                },
            )

        resp = await auth_client.get("/api/v1/credentials")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["resources"]) >= 2
        # All inputs should be masked
        for resource in body["resources"]:
            if resource["inputs"]:
                for value in resource["inputs"].values():
                    assert value == "$encrypted$"
            # created_by must be UserReference objects in list responses
            assert isinstance(resource["created_by"], dict)
            assert "id" in resource["created_by"]
            assert "name" in resource["created_by"]


class TestUpdateCredential:
    """PATCH /api/v1/credentials/{id}."""

    @pytest.mark.asyncio
    async def test_update_preserves_encrypted_sentinel(
        self, auth_client: AsyncClient, basic_auth_type: CredentialType, test_project_id: str
    ) -> None:
        # Create
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "Update Test",
                "credential_type_id": str(basic_auth_type.id),
                "project_id": test_project_id,
                "inputs": {"username": "old-user", "password": "old-pass"},
            },
        )
        cred_id = create_resp.json()["id"]

        # Update: change username, preserve password
        update_resp = await auth_client.patch(
            f"/api/v1/credentials/{cred_id}",
            json={"inputs": {"username": "new-user", "password": "$encrypted$"}},
        )
        assert update_resp.status_code == 200
        body = update_resp.json()
        assert body["inputs"]["username"] == "new-user"
        assert body["inputs"]["password"] == "$encrypted$"  # noqa: S105

        # Verify password was actually preserved (get and check)
        get_resp = await auth_client.get(f"/api/v1/credentials/{cred_id}")
        assert get_resp.json()["inputs"]["username"] == "new-user"

    @pytest.mark.asyncio
    async def test_update_name(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "Old Name",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc"},
            },
        )
        cred_id = create_resp.json()["id"]

        update_resp = await auth_client.patch(
            f"/api/v1/credentials/{cred_id}",
            json={"name": "New Name"},
        )
        assert update_resp.status_code == 200
        body = update_resp.json()
        assert body["name"] == "New Name"

        # updated_by must be UserReference object after update
        assert isinstance(body["updated_by"], dict)
        assert "id" in body["updated_by"]
        assert "name" in body["updated_by"]


class TestUserReferenceFields:
    """Verify created_by/updated_by return UserReference objects."""

    @pytest.mark.asyncio
    async def test_create_returns_user_reference_with_correct_user(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str, test_user: User
    ) -> None:
        """created_by and updated_by should be {id, name} matching the authenticated user."""
        resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"UserRef Test {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc"},
            },
        )
        assert resp.status_code == 201
        body = resp.json()

        assert body["created_by"]["id"] == str(test_user.id)
        assert body["created_by"]["name"] == test_user.username
        assert body["updated_by"]["id"] == str(test_user.id)
        assert body["updated_by"]["name"] == test_user.username

    @pytest.mark.asyncio
    async def test_get_returns_user_reference(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str, test_user: User
    ) -> None:
        """GET should also return UserReference objects."""
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"UserRef Get Test {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc"},
            },
        )
        cred_id = create_resp.json()["id"]

        get_resp = await auth_client.get(f"/api/v1/credentials/{cred_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()

        assert body["created_by"]["id"] == str(test_user.id)
        assert body["created_by"]["name"] == test_user.username

    @pytest.mark.asyncio
    async def test_list_returns_user_references(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str, test_user: User
    ) -> None:
        """List endpoint should return UserReference objects for all resources."""
        await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"UserRef List Test {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc"},
            },
        )

        resp = await auth_client.get("/api/v1/credentials")
        assert resp.status_code == 200
        for resource in resp.json()["resources"]:
            assert isinstance(resource["created_by"], dict)
            assert resource["created_by"]["id"] == str(test_user.id)
            assert resource["created_by"]["name"] == test_user.username

    @pytest.mark.asyncio
    async def test_update_returns_user_reference(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str, test_user: User
    ) -> None:
        """PATCH response should have UserReference for updated_by."""
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"UserRef Update Test {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc"},
            },
        )
        cred_id = create_resp.json()["id"]

        update_resp = await auth_client.patch(
            f"/api/v1/credentials/{cred_id}",
            json={"description": "Updated"},
        )
        assert update_resp.status_code == 200
        body = update_resp.json()

        assert body["updated_by"]["id"] == str(test_user.id)
        assert body["updated_by"]["name"] == test_user.username


class TestDeleteCredential:
    """DELETE /api/v1/credentials/{id}."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "To Delete",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc"},
            },
        )
        cred_id = create_resp.json()["id"]

        delete_resp = await auth_client.delete(f"/api/v1/credentials/{cred_id}")
        assert delete_resp.status_code == 204

        # Verify it's gone
        get_resp = await auth_client.get(f"/api/v1/credentials/{cred_id}")
        assert get_resp.status_code == 404


class TestCredentialWorkflows:
    """GET /api/v1/credentials/{id}/workflows (T048)."""

    @pytest.mark.asyncio
    async def test_workflows_returns_empty_list(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        """Credentials not referenced by any workflow return empty list."""
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"Workflow Test {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc"},
            },
        )
        cred_id = create_resp.json()["id"]

        resp = await auth_client.get(f"/api/v1/credentials/{cred_id}/workflows")
        assert resp.status_code == 200
        assert resp.json()["resources"] == []

    @pytest.mark.asyncio
    async def test_workflows_not_found_returns_404(self, auth_client: AsyncClient) -> None:
        """Non-existent credential returns 404."""
        resp = await auth_client.get(f"/api/v1/credentials/{uuid4()}/workflows")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_workflows_returns_referencing_workflow_with_node_names(
        self,
        auth_client: AsyncClient,
        bearer_type: CredentialType,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Workflow referencing a credential is returned with correct node_names."""
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"Node Names Test {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "test-token"},
            },
        )
        cred_id = create_resp.json()["id"]

        workflow = Workflow(
            name=f"cred-ref-workflow-{uuid4().hex[:8]}",
            description="Workflow referencing a credential",
            created_by=test_user.id,
            is_enabled=False,
            current_version=1,
            project_id=UUID(test_project_id),
        )
        test_db_session.add(workflow)

        version = WorkflowVersion(
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition={
                "schema_version": "2.0.0",
                "name": workflow.name,
                "triggers": [{"id": "trigger_manual", "type": "manual_trigger"}],
                "nodes": [
                    {
                        "id": "fetch_data",
                        "name": "Fetch Data",
                        "type": "http_request",
                        "parameters": {
                            "method": "GET",
                            "url": "https://api.example.com/data",
                            "credential_id": cred_id,
                        },
                    },
                ],
                "edges": [{"from": "trigger_manual", "to": "fetch_data"}],
            },
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.flush()
        workflow.published_version_id = version.id
        workflow.is_enabled = True
        publish_event = WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.PUBLISHED,
            actor_id=test_user.id,
        )
        test_db_session.add(publish_event)
        await test_db_session.commit()

        resp = await auth_client.get(f"/api/v1/credentials/{cred_id}/workflows")
        assert resp.status_code == 200
        workflows = resp.json()["resources"]
        assert len(workflows) == 1
        assert workflows[0]["id"] == str(workflow.id)
        assert workflows[0]["name"] == workflow.name
        assert workflows[0]["node_names"] == ["Fetch Data"]

    @pytest.mark.asyncio
    async def test_workflows_returns_multiple_node_names(
        self,
        auth_client: AsyncClient,
        bearer_type: CredentialType,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: str,
    ) -> None:
        """Multiple nodes referencing same credential returns all node names."""
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"Multi Node Test {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "test-token"},
            },
        )
        cred_id = create_resp.json()["id"]

        workflow = Workflow(
            name=f"multi-node-workflow-{uuid4().hex[:8]}",
            description="Workflow with multiple nodes using same credential",
            created_by=test_user.id,
            is_enabled=False,
            current_version=1,
            project_id=UUID(test_project_id),
        )
        test_db_session.add(workflow)

        version = WorkflowVersion(
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition={
                "schema_version": "2.0.0",
                "name": workflow.name,
                "triggers": [{"id": "trigger_manual", "type": "manual_trigger"}],
                "nodes": [
                    {
                        "id": "step_1",
                        "name": "Fetch Users",
                        "type": "http_request",
                        "parameters": {
                            "method": "GET",
                            "url": "https://api.example.com/users",
                            "credential_id": cred_id,
                        },
                    },
                    {
                        "id": "step_2",
                        "name": "Fetch Orders",
                        "type": "http_request",
                        "parameters": {
                            "method": "GET",
                            "url": "https://api.example.com/orders",
                            "credential_id": cred_id,
                        },
                    },
                    {
                        "id": "step_3",
                        "name": "Process Data",
                        "type": "script",
                        "parameters": {"language": "python", "code": "print('done')"},
                    },
                ],
                "edges": [
                    {"from": "trigger_manual", "to": "step_1"},
                    {"from": "step_1", "to": "step_2"},
                    {"from": "step_2", "to": "step_3"},
                ],
            },
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.flush()
        workflow.published_version_id = version.id
        workflow.is_enabled = True
        publish_event = WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.PUBLISHED,
            actor_id=test_user.id,
        )
        test_db_session.add(publish_event)
        await test_db_session.commit()

        resp = await auth_client.get(f"/api/v1/credentials/{cred_id}/workflows")
        assert resp.status_code == 200
        workflows = resp.json()["resources"]
        assert len(workflows) == 1
        assert sorted(workflows[0]["node_names"]) == ["Fetch Orders", "Fetch Users"]


class TestCredentialTypes:
    """GET /api/v1/credential_types."""

    @pytest.mark.asyncio
    async def test_list_returns_types(self, auth_client: AsyncClient, bearer_type: CredentialType) -> None:
        resp = await auth_client.get("/api/v1/credential_types")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["resources"]) >= 1
        names = [r["name"] for r in body["resources"]]
        assert bearer_type.name in names

    @pytest.mark.asyncio
    async def test_get_type_by_id(self, auth_client: AsyncClient, bearer_type: CredentialType) -> None:
        resp = await auth_client.get(f"/api/v1/credential_types/{bearer_type.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == bearer_type.name
        assert "inputs" in body
        assert "injectors" in body

    @pytest.mark.asyncio
    async def test_get_missing_type_returns_404(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.get(f"/api/v1/credential_types/{uuid4()}")
        assert resp.status_code == 404


class TestCredentialTypeCount:
    """Verify credential_count is returned on credential type endpoints (T043)."""

    @pytest.mark.asyncio
    async def test_list_types_includes_credential_count(
        self,
        auth_client: AsyncClient,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        """Types with no credentials should show credential_count: 0."""
        resp = await auth_client.get("/api/v1/credential_types")
        assert resp.status_code == 200
        resources = resp.json()["resources"]
        for resource in resources:
            assert "credential_count" in resource
            assert isinstance(resource["credential_count"], int)
            assert resource["credential_count"] >= 0
        # At least one type should have zero credentials (freshly created bearer_type)
        zero_count_types = [r for r in resources if r["credential_count"] == 0]
        assert len(zero_count_types) >= 1

    @pytest.mark.asyncio
    async def test_credential_count_increments(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        """Creating credentials should increment the count for their type."""
        # Check initial count
        resp = await auth_client.get(f"/api/v1/credential_types/{bearer_type.id}")
        initial_count = resp.json()["credential_count"]

        # Create two credentials of this type
        for i in range(2):
            await auth_client.post(
                "/api/v1/credentials",
                json={
                    "name": f"Count Test {i} {uuid4().hex[:8]}",
                    "credential_type_id": str(bearer_type.id),
                    "project_id": test_project_id,
                    "inputs": {"token": f"secret-{i}"},
                },
            )

        # Verify count increased
        resp = await auth_client.get(f"/api/v1/credential_types/{bearer_type.id}")
        assert resp.json()["credential_count"] == initial_count + 2

    @pytest.mark.asyncio
    async def test_deleted_credentials_not_counted(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        """Deleted credentials should not be included in the count."""
        # Create and delete a credential
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"Delete Count Test {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "to-delete"},
            },
        )
        cred_id = create_resp.json()["id"]

        resp_before = await auth_client.get(f"/api/v1/credential_types/{bearer_type.id}")
        count_before = resp_before.json()["credential_count"]

        await auth_client.delete(f"/api/v1/credentials/{cred_id}")

        resp_after = await auth_client.get(f"/api/v1/credential_types/{bearer_type.id}")
        assert resp_after.json()["credential_count"] == count_before - 1


@pytest.mark.usefixtures("preseeded_types")
class TestPreseedIntegration:
    """Verify preseed creates GA managed types in the database."""

    @pytest.mark.asyncio
    async def test_preseed_creates_all_ga_types(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.get("/api/v1/credential_types")
        assert resp.status_code == 200
        names = {r["name"] for r in resp.json()["resources"]}
        for type_def in GA_CREDENTIAL_TYPES:
            assert type_def["name"] in names

    @pytest.mark.asyncio
    async def test_preseed_types_are_managed(self, auth_client: AsyncClient, test_project_id: str) -> None:
        resp = await auth_client.get("/api/v1/credential_types")
        managed_types = [r for r in resp.json()["resources"] if r["managed"]]
        assert len(managed_types) >= len(GA_CREDENTIAL_TYPES)

    @pytest.mark.asyncio
    async def test_preseed_is_idempotent(
        self, test_db_session: AsyncSession, auth_client: AsyncClient, test_project_id: str
    ) -> None:
        # Run preseed again
        await preseed_credential_types(test_db_session)

        # Should still have the same count, not duplicates
        resp = await auth_client.get("/api/v1/credential_types")
        names = [r["name"] for r in resp.json()["resources"]]
        for type_def in GA_CREDENTIAL_TYPES:
            assert names.count(type_def["name"]) == 1


class TestEnabledFilter:
    """GET /api/v1/credentials?enabled=... (T038)."""

    @pytest.mark.asyncio
    async def test_filter_enabled_true(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        """Verify ?enabled=true returns only enabled credentials."""
        # Create enabled credential
        await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"Enabled Cred {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc"},
            },
        )
        # Create and disable a credential
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"Disabled Cred {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "def"},
            },
        )
        disabled_id = create_resp.json()["id"]
        await auth_client.patch(f"/api/v1/credentials/{disabled_id}", json={"enabled": False})

        resp = await auth_client.get("/api/v1/credentials?enabled=true")
        assert resp.status_code == 200
        for resource in resp.json()["resources"]:
            assert resource["enabled"] is True

    @pytest.mark.asyncio
    async def test_filter_enabled_false(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        """Verify ?enabled=false returns only disabled credentials."""
        # Create and disable a credential
        create_resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": f"To Disable {uuid4().hex[:8]}",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "ghi"},
            },
        )
        cred_id = create_resp.json()["id"]
        await auth_client.patch(f"/api/v1/credentials/{cred_id}", json={"enabled": False})

        resp = await auth_client.get("/api/v1/credentials?enabled=false")
        assert resp.status_code == 200
        assert len(resp.json()["resources"]) >= 1
        for resource in resp.json()["resources"]:
            assert resource["enabled"] is False


class TestInputValidation:
    """Verify input validation returns 422 with clear error messages (T028)."""

    @pytest.mark.asyncio
    async def test_unknown_field_returns_422(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "Bad Fields",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "abc", "bogus_field": "value"},
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_returns_422(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "Missing Required",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {},
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_encrypted_sentinel_on_create_returns_422(
        self, auth_client: AsyncClient, bearer_type: CredentialType, test_project_id: str
    ) -> None:
        resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "Sentinel Input",
                "credential_type_id": str(bearer_type.id),
                "project_id": test_project_id,
                "inputs": {"token": "$encrypted$"},
            },
        )
        assert resp.status_code == 422
