"""Subscribe bindings reuse resource access rules on save and import."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.core.exceptions import SafeValueError
from syntara.credentials.models.credential import Credential
from syntara.integrations.exceptions import IntegrationCredentialTypeMismatchError
from syntara.integrations.models.integration import Integration, IntegrationScope
from syntara.workflows.services.workflow_service import WorkflowService
from syntara.workflows.validators.workflow_integrations import (
    _extract_integration_ids,
    _validate_integration_scope,
    validate_workflow_references,
)

SERVICE = "syntara.workflows.services.workflow_service"


@pytest.fixture
def definition() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "Subscribe",
        "nodes": [],
        "edges": [],
        "triggers": [
            {
                "id": "incoming",
                "type": "event_subscribe_trigger",
                "parameters": {
                    "integration_id": str(uuid4()),
                    "credential_id": str(uuid4()),
                    "topic": "alerts",
                },
            }
        ],
    }


@pytest.fixture
def service() -> WorkflowService:
    user = MagicMock(id=uuid4(), labels={}, authz_metadata={})
    return WorkflowService(AsyncMock(), user, MagicMock())


def test_trigger_reference_extraction(definition: dict[str, Any]) -> None:
    params = definition["triggers"][0]["parameters"]
    assert _extract_integration_ids(definition) == {params["integration_id"]}
    assert WorkflowService._extract_credential_ids(definition) == {params["credential_id"]}


@pytest.mark.parametrize("rows", [[], [(uuid4(), uuid4())]])
async def test_missing_or_cross_project_credential_rejected(
    service: WorkflowService,
    definition: dict[str, Any],
    rows: list[tuple[UUID, UUID]],
) -> None:
    result = MagicMock()
    result.all.return_value = rows
    cast("AsyncMock", service.session).exec.return_value = result
    with pytest.raises(SafeValueError, match="credential references"):
        await service._validate_credential_project_scope(definition, uuid4())


async def test_actor_must_have_credential_use(service: WorkflowService, definition: dict[str, Any]) -> None:
    params = definition["triggers"][0]["parameters"]
    project_id = uuid4()
    result = MagicMock()
    result.all.return_value = [(UUID(params["credential_id"]), project_id)]
    result.first.return_value = "destination"
    cast("AsyncMock", service.session).exec.return_value = result
    with (
        patch(f"{SERVICE}.authorize", return_value=SimpleNamespace(allowed=False)) as authorize,
        pytest.raises(AuthorizationDeniedError),
    ):
        await service._validate_credential_project_scope(definition, project_id)
    request = authorize.call_args.args[2]
    assert request.action == "use"
    assert request.resource_id == params["credential_id"]
    assert request.resource_project == "destination"


async def test_unknown_account_field_rejected_before_resource_lookup(
    service: WorkflowService,
    definition: dict[str, Any],
) -> None:
    definition["triggers"][0]["parameters"]["execution_account_id"] = str(uuid4())
    with pytest.raises(SafeValueError, match="Subscribe parameters"):
        await service._validate_credential_project_scope(definition, uuid4())
    cast("AsyncMock", service.session).exec.assert_not_called()


@pytest.mark.parametrize("visible", [True, False])
async def test_actor_visibility_and_credential_compatibility_delegation(
    service: WorkflowService,
    definition: dict[str, Any],
    *,
    visible: bool,
) -> None:
    params = definition["triggers"][0]["parameters"]
    integration_id = UUID(params["integration_id"])
    credential_id = UUID(params["credential_id"])
    cast("AsyncMock", service.session).get.side_effect = [
        SimpleNamespace(integration_type="kafka", enabled=True),
        SimpleNamespace(enabled=True),
    ]
    with (
        patch(
            f"{SERVICE}.resolve_allowed_projects", return_value=AllowedProjectsResult(all_projects=True, project_ids=[])
        ),
        patch(f"{SERVICE}.IntegrationService.resolve_visible_integration_ids", return_value=None if visible else []),
        patch(f"{SERVICE}.IntegrationService._validate_credential_type", new_callable=AsyncMock) as validate_type,
    ):
        if visible:
            await service._validate_event_subscribe_bindings(definition)
            validate_type.assert_awaited_once_with("kafka", credential_id)
            cast("AsyncMock", service.session).get.assert_any_await(Integration, integration_id)
            cast("AsyncMock", service.session).get.assert_any_await(Credential, credential_id)
        else:
            with pytest.raises(SafeValueError, match="not visible"):
                await service._validate_event_subscribe_bindings(definition)
            validate_type.assert_not_called()


async def test_credential_type_error_propagates(service: WorkflowService, definition: dict[str, Any]) -> None:
    cast("AsyncMock", service.session).get.side_effect = [
        SimpleNamespace(integration_type="kafka", enabled=True),
        SimpleNamespace(enabled=True),
    ]
    error = IntegrationCredentialTypeMismatchError("kafka", "HTTP Basic Auth", frozenset({"Kafka"}))
    with (
        patch(
            f"{SERVICE}.resolve_allowed_projects", return_value=AllowedProjectsResult(all_projects=True, project_ids=[])
        ),
        patch(f"{SERVICE}.IntegrationService.resolve_visible_integration_ids", return_value=None),
        patch(f"{SERVICE}.IntegrationService._validate_credential_type", side_effect=error),
        pytest.raises(IntegrationCredentialTypeMismatchError),
    ):
        await service._validate_event_subscribe_bindings(definition)


async def test_actor_without_integration_read_rejected(service: WorkflowService, definition: dict[str, Any]) -> None:
    with (
        patch(
            f"{SERVICE}.resolve_allowed_projects",
            return_value=AllowedProjectsResult(all_projects=False, project_ids=[]),
        ),
        pytest.raises(AuthorizationDeniedError),
    ):
        await service._validate_event_subscribe_bindings(definition)


@pytest.mark.parametrize("read_all_projects", [False, True])
async def test_scoped_visibility_without_read_all(
    service: WorkflowService,
    definition: dict[str, Any],
    *,
    read_all_projects: bool,
) -> None:
    project_id = uuid4()
    scope = AllowedProjectsResult(all_projects=False, project_ids=[project_id])
    memberships = MagicMock()
    memberships.scalars.return_value.all.return_value = [project_id]
    cast("AsyncMock", service.session).execute.return_value = memberships
    cast("AsyncMock", service.session).get.side_effect = [
        SimpleNamespace(integration_type="kafka", enabled=True),
        SimpleNamespace(enabled=True),
    ]
    with (
        patch(
            f"{SERVICE}.resolve_allowed_projects",
            side_effect=[
                AllowedProjectsResult(all_projects=True, project_ids=[]) if read_all_projects else scope,
                AllowedProjectsResult(all_projects=False, project_ids=[]),
            ],
        ),
        patch(
            f"{SERVICE}.IntegrationService.resolve_visible_integration_ids",
            return_value=[UUID(definition["triggers"][0]["parameters"]["integration_id"])],
        ) as visibility,
        patch(f"{SERVICE}.IntegrationService._validate_credential_type", new_callable=AsyncMock),
    ):
        await service._validate_event_subscribe_bindings(definition)
    visibility.assert_awaited_once_with(service.session, scope)


@pytest.mark.parametrize("resource", ["integration", "credential", "disabled_integration", "disabled_credential"])
async def test_unavailable_runtime_bindings_rejected(
    service: WorkflowService,
    definition: dict[str, Any],
    resource: str,
) -> None:
    cast("AsyncMock", service.session).get.side_effect = [
        None
        if resource == "integration"
        else SimpleNamespace(integration_type="kafka", enabled=resource != "disabled_integration"),
        None if resource == "credential" else SimpleNamespace(enabled=resource != "disabled_credential"),
    ]
    with (
        patch(
            f"{SERVICE}.resolve_allowed_projects", return_value=AllowedProjectsResult(all_projects=True, project_ids=[])
        ),
        patch(f"{SERVICE}.IntegrationService.resolve_visible_integration_ids", return_value=None),
        patch(f"{SERVICE}.IntegrationService._validate_credential_type", new_callable=AsyncMock) as validate_type,
        pytest.raises(SafeValueError, match="Event Subscribe resource references are unavailable"),
    ):
        await service._validate_event_subscribe_bindings(definition)
    validate_type.assert_not_awaited()


@pytest.mark.parametrize("missing", [True, False])
async def test_integration_must_exist_and_be_assigned_to_destination(
    definition: dict[str, Any],
    *,
    missing: bool,
) -> None:
    session = AsyncMock()
    row = SimpleNamespace(
        id=UUID(definition["triggers"][0]["parameters"]["integration_id"]),
        scope=IntegrationScope.PROJECT,
        enabled=True,
        name="source",
    )
    integrations, assignments = MagicMock(), MagicMock()
    integrations.all.return_value = [] if missing else [row]
    assignments.scalars.return_value.all.return_value = []
    session.execute.side_effect = [integrations, assignments]
    with pytest.raises(SafeValueError, match="no longer available" if missing else "not accessible"):
        await _validate_integration_scope(session, definition, uuid4(), set())


async def test_incompatible_integration_rejected(definition: dict[str, Any]) -> None:
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(integration_type="mcp_server")
    with (
        patch("syntara.workflows.validators.workflow_integrations._validate_integration_scope", new_callable=AsyncMock),
        pytest.raises(SafeValueError, match="Integration type"),
    ):
        await validate_workflow_references(session, definition, uuid4())


@pytest.mark.parametrize("is_import", [False, True])
async def test_reference_checks_run_for_destination_on_save_and_import(
    definition: dict[str, Any],
    *,
    is_import: bool,
) -> None:
    session = AsyncMock()
    destination = uuid4()
    with (
        patch(
            "syntara.workflows.validators.workflow_integrations._validate_llm_model_references",
            return_value=(set(), []),
        ),
        patch(
            "syntara.workflows.validators.workflow_integrations._extract_tool_parent_integration_ids",
            return_value=set(),
        ),
        patch(
            "syntara.workflows.validators.workflow_integrations._validate_integration_scope",
            side_effect=SafeValueError("not accessible"),
        ) as validate_scope,
        pytest.raises(SafeValueError, match="not accessible"),
    ):
        await validate_workflow_references(session, definition, destination, is_import=is_import)
    validate_scope.assert_awaited_once_with(session, definition, destination, set())


async def test_import_create_uses_destination_reference_checks(
    service: WorkflowService,
    definition: dict[str, Any],
) -> None:
    destination = uuid4()
    cast("AsyncMock", service.session).get.return_value = SimpleNamespace(is_builtin=False)
    with (
        patch("syntara.core.queries.project_queries.assert_project_alive", new_callable=AsyncMock),
        patch(f"{SERVICE}.get_system_continue_on_failure", return_value=False),
        patch.object(service, "_validate_credential_project_scope", new_callable=AsyncMock) as credentials,
        patch(f"{SERVICE}.validate_workflow_references", side_effect=SafeValueError("not accessible")) as references,
        pytest.raises(SafeValueError, match="not accessible"),
    ):
        await service.create_workflow("Imported", None, {}, definition, destination, is_import=True)
    credentials.assert_awaited_once_with(definition, destination)
    references.assert_awaited_once_with(service.session, definition, destination, is_import=True)
