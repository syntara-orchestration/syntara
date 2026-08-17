"""E2E tests for integration project scope enforcement."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution_until_complete
from orchestrator_test_sdk.factories.credentials import get_bearer_token_type_id
from syntara_api_client.models import (
    ExecutionCreate,
    WorkflowCreate,
    WorkflowDefinition,
)
from syntara_api_client.models.credential_create import CredentialCreate
from syntara_api_client.models.credential_create_inputs import CredentialCreateInputs
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.integration_create import IntegrationCreate
from syntara_api_client.models.integration_scope import IntegrationScope
from syntara_api_client.models.integration_type import IntegrationType
from syntara_api_client.models.integration_update import IntegrationUpdate
from syntara_api_client.models.mcp_server_configuration_input import MCPServerConfigurationInput
from syntara_api_client.models.project_create import ProjectCreate

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import WorkflowRead

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

pytestmark = [pytest.mark.e2e]


def _create_credential(syntara_api: SyntaraApiRegistry, project_id: UUID) -> UUID:
    """Create a bearer-token credential in the given project, return its UUID."""
    type_id = get_bearer_token_type_id(syntara_api)
    cred = syntara_api.credentials.create(
        body=CredentialCreate(
            name=unique_name("e2e-scope-cred"),
            credential_type_id=type_id,
            project_id=project_id,
            inputs=CredentialCreateInputs.from_dict({"token": "e2e-dummy-token"}),
        ),
    ).assert_and_get()
    return UUID(str(cred.id))


def _agentic_workflow_definition(name: str, integration_id: str, credential_id: str) -> WorkflowDefinition:
    """Build a minimal workflow with a trigger and agentic node referencing an MCP integration."""
    return WorkflowDefinition.from_dict(
        {
            "schema_version": "2.0.0",
            "name": name,
            "description": "Scope enforcement E2E test workflow",
            "triggers": [
                {
                    "id": "trigger_manual",
                    "type": "manual_trigger",
                    "parameters": {},
                },
            ],
            "nodes": [
                {
                    "id": "agent_node",
                    "name": "Test Agent",
                    "type": "agentic",
                    "parameters": {
                        "prompt": "test scope enforcement",
                        "integration_connections": [
                            {
                                "integration_id": integration_id,
                                "credential_id": credential_id,
                            },
                        ],
                    },
                },
            ],
            "edges": [{"from": "trigger_manual", "to": "agent_node"}],
        }
    )


class TestExecutionTimeScopeViolation:
    """Execution-time scope violation when an integration is unassigned from a project."""

    def test_unassigned_integration_causes_execution_failure(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        integration_factory: Callable[..., dict[str, Any]],
        first_project_id: UUID,
    ) -> None:
        """Unassigning a project-scoped integration causes workflow execution to fail.

        Steps:
        1. Create project-scoped MCP integration assigned to first_project_id
        2. Create credential + workflow referencing the integration
        3. Unassign the integration from the project
        4. Execute → poll → assert scope violation failure
        """
        integration = integration_factory(
            IntegrationCreate(
                name=unique_name("e2e-scope-violation"),
                integration_type=IntegrationType.MCP_SERVER,
                configuration=MCPServerConfigurationInput(
                    base_url="https://example.com",
                ),
                scope=IntegrationScope.PROJECT,
            )
        )
        integration_id = UUID(integration["id"])

        resp = syntara_api.integrations.assign_project(
            integration_id=integration_id,
            project_id=first_project_id,
        )
        assert resp.status_code in (HTTPStatus.CREATED, HTTPStatus.OK), f"Failed to assign project: {resp.status_code}"

        credential_id = _create_credential(syntara_api, first_project_id)
        try:
            workflow_name = unique_name("e2e-scope-violation-wf")
            workflow = workflow_factory(
                WorkflowCreate(
                    name=workflow_name,
                    description="Workflow for scope violation test",
                    project_id=first_project_id,
                    workflow_definition=_agentic_workflow_definition(
                        workflow_name, str(integration_id), str(credential_id)
                    ),
                )
            )

            unassign_resp = syntara_api.integrations.unassign_project(
                integration_id=integration_id,
                project_id=first_project_id,
            )
            assert unassign_resp.status_code == HTTPStatus.NO_CONTENT

            execution = syntara_api.executions.create(
                body=ExecutionCreate(
                    workflow_id=workflow.id,
                    trigger_node_id="trigger_manual",
                )
            ).assert_and_get()

            result = poll_execution_until_complete(
                syntara_api,
                UUID(str(execution.id)),
                max_polls=30,
                poll_interval=2,
            )

            assert result.status == ExecutionStatus.FAILED, f"Expected FAILED, got {result.status}"
            error_text = str(result.error_details or "")
            assert "IntegrationNotAccessibleError" in error_text or "not accessible" in error_text.lower(), (
                f"Expected IntegrationNotAccessibleError, got: {result.error_details}"
            )
        finally:
            try:
                syntara_api.credentials.delete(credential_id=credential_id)
            except Exception:
                pass


class TestNarrowGlobalToProjectScoped:
    """Narrowing a global integration to project-scoped restricts visibility and execution."""

    def test_narrowing_global_removes_from_excluded_project_and_fails_execution(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        integration_factory: Callable[..., dict[str, Any]],
        first_project_id: UUID,
    ) -> None:
        """Restricting a global integration to project A excludes it from project B.

        Also causes execution failure for project B workflows.

        Steps:
        1. Create global integration, create project B
        2. Verify integration visible for both projects
        3. Create credential + workflow in project B referencing integration
        4. Narrow scope to project A only
        5. Verify integration gone from project B list, still in project A
        6. Execute project B workflow → assert scope violation failure
        """
        integration = integration_factory(
            IntegrationCreate(
                name=unique_name("e2e-narrow-scope"),
                integration_type=IntegrationType.MCP_SERVER,
                configuration=MCPServerConfigurationInput(
                    base_url="https://example.com",
                ),
                scope=IntegrationScope.GLOBAL,
            )
        )
        integration_id = UUID(integration["id"])

        project_b = syntara_api.projects.create(body=ProjectCreate(name=unique_name("e2e-project-b"))).assert_and_get()
        project_b_id = UUID(str(project_b.id))

        credential_id: UUID | None = None
        try:
            list_a = syntara_api.integrations.list(
                integration_type=IntegrationType.MCP_SERVER,
                project_id=first_project_id,
            ).assert_and_get()
            ids_a = {str(r.id) for r in list_a.resources}
            assert str(integration_id) in ids_a, "Global integration should be visible in project A"

            list_b = syntara_api.integrations.list(
                integration_type=IntegrationType.MCP_SERVER,
                project_id=project_b_id,
            ).assert_and_get()
            ids_b = {str(r.id) for r in list_b.resources}
            assert str(integration_id) in ids_b, "Global integration should be visible in project B"

            credential_id = _create_credential(syntara_api, project_b_id)

            workflow_name = unique_name("e2e-narrow-scope-wf")
            workflow = workflow_factory(
                WorkflowCreate(
                    name=workflow_name,
                    description="Workflow for narrow scope test",
                    project_id=project_b_id,
                    workflow_definition=_agentic_workflow_definition(
                        workflow_name, str(integration_id), str(credential_id)
                    ),
                )
            )

            syntara_api.integrations.update(
                integration_id=integration_id,
                body=IntegrationUpdate(scope=IntegrationScope.PROJECT),
            ).assert_and_get()
            syntara_api.integrations.assign_project(
                integration_id=integration_id,
                project_id=first_project_id,
            )

            list_b_after = syntara_api.integrations.list(
                integration_type=IntegrationType.MCP_SERVER,
                project_id=project_b_id,
            ).assert_and_get()
            ids_b_after = {str(r.id) for r in list_b_after.resources}
            assert str(integration_id) not in ids_b_after, "Integration should no longer be visible in project B"

            list_a_after = syntara_api.integrations.list(
                integration_type=IntegrationType.MCP_SERVER,
                project_id=first_project_id,
            ).assert_and_get()
            ids_a_after = {str(r.id) for r in list_a_after.resources}
            assert str(integration_id) in ids_a_after, "Integration should still be visible in project A"

            execution = syntara_api.executions.create(
                body=ExecutionCreate(
                    workflow_id=workflow.id,
                    trigger_node_id="trigger_manual",
                )
            ).assert_and_get()

            result = poll_execution_until_complete(
                syntara_api,
                UUID(str(execution.id)),
                max_polls=30,
                poll_interval=2,
            )

            assert result.status == ExecutionStatus.FAILED, (
                f"Expected FAILED after scope narrowing, got {result.status}"
            )
            error_text = str(result.error_details or "")
            assert "IntegrationNotAccessibleError" in error_text or "not accessible" in error_text.lower(), (
                f"Expected IntegrationNotAccessibleError, got: {result.error_details}"
            )

        finally:
            try:
                if credential_id:
                    syntara_api.credentials.delete(credential_id=credential_id)
            except Exception:
                pass
            try:
                syntara_api.projects.delete(project_id=project_b_id)
            except Exception:
                pass


class TestExecutionTimeIntegrationStateErrors:
    """Execution-time errors for disabled and deleted integrations produce distinct messages."""

    def test_disabled_integration_produces_disabled_error(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        integration_factory: Callable[..., dict[str, Any]],
        first_project_id: UUID,
    ) -> None:
        """Disabling an integration after workflow creation causes execution to fail.

        Steps:
        1. Create project-scoped MCP integration assigned to first_project_id
        2. Create credential + workflow referencing the integration
        3. Disable the integration
        4. Execute → poll → assert IntegrationDisabledError
        """
        integration = integration_factory(
            IntegrationCreate(
                name=unique_name("e2e-disabled-integ"),
                integration_type=IntegrationType.MCP_SERVER,
                configuration=MCPServerConfigurationInput(
                    base_url="https://example.com",
                ),
                scope=IntegrationScope.PROJECT,
            )
        )
        integration_id = UUID(integration["id"])

        resp = syntara_api.integrations.assign_project(
            integration_id=integration_id,
            project_id=first_project_id,
        )
        assert resp.status_code in (HTTPStatus.CREATED, HTTPStatus.OK)

        credential_id = _create_credential(syntara_api, first_project_id)
        try:
            workflow_name = unique_name("e2e-disabled-integ-wf")
            workflow = workflow_factory(
                WorkflowCreate(
                    name=workflow_name,
                    description="Workflow for disabled integration test",
                    project_id=first_project_id,
                    workflow_definition=_agentic_workflow_definition(
                        workflow_name, str(integration_id), str(credential_id)
                    ),
                )
            )

            syntara_api.integrations.update(
                integration_id=integration_id,
                body=IntegrationUpdate(enabled=False),
            ).assert_and_get()

            execution = syntara_api.executions.create(
                body=ExecutionCreate(
                    workflow_id=workflow.id,
                    trigger_node_id="trigger_manual",
                )
            ).assert_and_get()

            result = poll_execution_until_complete(
                syntara_api,
                UUID(str(execution.id)),
                max_polls=30,
                poll_interval=2,
            )

            assert result.status == ExecutionStatus.FAILED, (
                f"Expected FAILED after disabling integration, got {result.status}"
            )
            error_text = str(result.error_details or "")
            assert "IntegrationDisabledError" in error_text or "disabled" in error_text.lower(), (
                f"Expected IntegrationDisabledError, got: {result.error_details}"
            )
        finally:
            try:
                syntara_api.credentials.delete(credential_id=credential_id)
            except Exception:
                pass

    def test_deleted_integration_produces_not_found_error(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ) -> None:
        """Deleting an integration after workflow creation causes execution to fail.

        Steps:
        1. Create project-scoped MCP integration assigned to first_project_id
        2. Create credential + workflow referencing the integration
        3. Delete the integration
        4. Execute → poll → assert IntegrationNotFoundError
        """
        integration = syntara_api.integrations.create(
            body=IntegrationCreate(
                name=unique_name("e2e-deleted-integ"),
                integration_type=IntegrationType.MCP_SERVER,
                configuration=MCPServerConfigurationInput(
                    base_url="https://example.com",
                ),
                scope=IntegrationScope.PROJECT,
            )
        ).assert_and_get()
        integration_id = integration.id

        resp = syntara_api.integrations.assign_project(
            integration_id=integration_id,
            project_id=first_project_id,
        )
        assert resp.status_code in (HTTPStatus.CREATED, HTTPStatus.OK)

        credential_id = _create_credential(syntara_api, first_project_id)
        try:
            workflow_name = unique_name("e2e-deleted-integ-wf")
            workflow = workflow_factory(
                WorkflowCreate(
                    name=workflow_name,
                    description="Workflow for deleted integration test",
                    project_id=first_project_id,
                    workflow_definition=_agentic_workflow_definition(
                        workflow_name, str(integration_id), str(credential_id)
                    ),
                )
            )

            syntara_api.integrations.delete(integration_id=integration_id)

            execution = syntara_api.executions.create(
                body=ExecutionCreate(
                    workflow_id=workflow.id,
                    trigger_node_id="trigger_manual",
                )
            ).assert_and_get()

            result = poll_execution_until_complete(
                syntara_api,
                UUID(str(execution.id)),
                max_polls=30,
                poll_interval=2,
            )

            assert result.status == ExecutionStatus.FAILED, (
                f"Expected FAILED after deleting integration, got {result.status}"
            )
            error_text = str(result.error_details or "")
            assert "IntegrationNotFoundError" in error_text or "no longer available" in error_text.lower(), (
                f"Expected IntegrationNotFoundError, got: {result.error_details}"
            )
        finally:
            try:
                syntara_api.credentials.delete(credential_id=credential_id)
            except Exception:
                pass
