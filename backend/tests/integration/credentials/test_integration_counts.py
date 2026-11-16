"""Integration tests for CredentialService.get_integration_counts against a real database."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from syntara.core.models.secret import Secret
from syntara.credentials.models.credential import Credential
from syntara.credentials.services.credential_service import CredentialService
from syntara.integrations.models.integration import Integration, IntegrationScope, IntegrationType
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.credentials.models.credential_type import CredentialType


async def _create_credential(
    session: AsyncSession, user: User, cred_type: CredentialType, project_id: str
) -> Credential:
    secret = Secret()
    session.add(secret)
    await session.flush()

    cred = Credential(
        name=f"test-cred-{uuid4().hex[:8]}",
        credential_type_id=cred_type.id,
        secret_id=secret.id,
        enabled=True,
        project_id=project_id,
        created_by=user.id,
    )
    session.add(cred)
    await session.flush()
    return cred


async def _create_integration(
    session: AsyncSession,
    user: User,
    *,
    management_credential_id: str | None = None,
    deleted: bool = False,
) -> Integration:
    integration = Integration(
        name=f"test-int-{uuid4().hex[:8]}",
        integration_type=IntegrationType.MCP_SERVER,
        scope=IntegrationScope.GLOBAL,
        configuration={"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
        management_credential_id=management_credential_id,
        created_by=user.id,
    )
    session.add(integration)
    await session.flush()
    if deleted:
        await session.delete(integration)
        await session.flush()
    return integration


@pytest.mark.asyncio
class TestGetIntegrationCountsIntegration:
    """Verify get_integration_counts SQL query against a real database."""

    async def test_counts_integrations_per_credential(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        cred1 = await _create_credential(test_db_session, test_user, bearer_type, test_project_id)
        cred2 = await _create_credential(test_db_session, test_user, bearer_type, test_project_id)

        await _create_integration(test_db_session, test_user, management_credential_id=str(cred1.id))
        await _create_integration(test_db_session, test_user, management_credential_id=str(cred1.id))
        await _create_integration(test_db_session, test_user, management_credential_id=str(cred2.id))

        await test_db_session.commit()

        service = CredentialService(test_db_session, test_user, MagicMock())
        result = await service.get_integration_counts([cred1.id, cred2.id])

        assert result[cred1.id] == 2
        assert result[cred2.id] == 1

    async def test_excludes_deleted_integrations(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        cred = await _create_credential(test_db_session, test_user, bearer_type, test_project_id)

        await _create_integration(test_db_session, test_user, management_credential_id=str(cred.id))
        await _create_integration(test_db_session, test_user, management_credential_id=str(cred.id), deleted=True)

        await test_db_session.commit()

        service = CredentialService(test_db_session, test_user, MagicMock())
        result = await service.get_integration_counts([cred.id])

        assert result.get(cred.id, 0) == 1

    async def test_ignores_integrations_with_null_credential(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        cred = await _create_credential(test_db_session, test_user, bearer_type, test_project_id)

        await _create_integration(test_db_session, test_user, management_credential_id=str(cred.id))
        await _create_integration(test_db_session, test_user, management_credential_id=None)

        await test_db_session.commit()

        service = CredentialService(test_db_session, test_user, MagicMock())
        result = await service.get_integration_counts([cred.id])

        assert result[cred.id] == 1

    async def test_returns_empty_for_credential_with_no_integrations(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        cred = await _create_credential(test_db_session, test_user, bearer_type, test_project_id)
        await test_db_session.commit()

        service = CredentialService(test_db_session, test_user, MagicMock())
        result = await service.get_integration_counts([cred.id])

        assert result.get(cred.id, 0) == 0


@pytest.mark.asyncio
class TestGetWorkflowCountsIntegration:
    """Verify workflow credential reference SQL against a real database."""

    async def test_counts_and_returns_credential_bindings(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        bearer_type: CredentialType,
        test_project_id: str,
    ) -> None:
        credential = await _create_credential(test_db_session, test_user, bearer_type, test_project_id)
        workflow = Workflow(
            name=f"binding-workflow-{uuid4().hex[:8]}",
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
                "triggers": [{"id": "trigger", "type": "manual_trigger"}],
                "nodes": [
                    {
                        "id": "script",
                        "name": "Run Script",
                        "type": "script",
                        "parameters": {
                            "language": "python",
                            "code": "print('done')",
                            "credential_bindings": [
                                {
                                    "credential_recipe_id": "example.token",
                                    "credential_ref": str(credential.id),
                                }
                            ],
                        },
                    }
                ],
                "edges": [{"from": "trigger", "to": "script"}],
            },
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.commit()

        service = CredentialService(test_db_session, test_user, MagicMock())
        assert await service.get_workflow_counts([credential.id]) == {credential.id: 1}
        references = await service.get_credential_workflows(credential.id)
        assert [reference.id for reference in references] == [workflow.id]
        assert references[0].node_names == ["Run Script"]
