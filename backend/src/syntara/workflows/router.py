"""Workflow API endpoints."""

import json
import re
from collections.abc import Callable, Coroutine
from io import BytesIO
from typing import Annotated, Any, overload
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import Response

from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import VisibilityResult
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.workflows.error_handlers import build_validation_problem_response
from syntara.workflows.exceptions import WorkflowDefinitionInvalidError
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.models import (
    DetailedValidationProblemDetail,
    PublishVersionRequest,
    PublishWorkflowVersionResponse,
    ValidationCategory,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
    Workflow,
    WorkflowCreate,
    WorkflowListParams,
    WorkflowListResponse,
    WorkflowRead,
    WorkflowReadWithVersion,
    WorkflowUpdate,
    WorkflowValidateRequest,
    WorkflowVersion,
    WorkflowVersionListParams,
    WorkflowVersionListResponse,
    WorkflowVersionRead,
    WorkflowVersionUpdate,
)
from syntara.workflows.models.execution import ExecutionRead, TestExecutionCreate
from syntara.workflows.models.workflow_definition import WorkflowDefinition
from syntara.workflows.services import ExecutionService, WorkflowService
from syntara.workflows.utils.serialization import deserialize_workflow_version
from syntara.workflows.validators import get_system_continue_on_failure, workflow_validator
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


def _has_validation_issues(result: ValidationResult) -> bool:
    """Return True when the validation result has errors or warnings."""
    return result.error_count > 0 or result.warning_count > 0


class _ValidationRoute(APIRoute):
    """Converts RequestValidationError into RFC 9457 problem details on 422."""

    def get_route_handler(self) -> Callable[..., Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                issues: list[str] = []
                for e in exc.errors():
                    path_parts = [str(p) for p in e["loc"]]
                    if path_parts and path_parts[0] == "body":
                        path_parts = path_parts[1:]
                    issues.append(f"{' -> '.join(path_parts)}: {e['msg']}")

                findings = [
                    ValidationFinding(
                        severity=ValidationSeverity.error,
                        category=ValidationCategory.schema_violation,
                        message=msg,
                    )
                    for msg in issues
                ]
                result = ValidationResult.from_findings(findings)
                return build_validation_problem_response(request, result)

        return handler


router = SyntaraRouter(prefix="/workflows", tags=["Workflows"])

_wf_perm_read = PermissionChecker(
    "workflow",
    "read",
    resource_model=Workflow,
    resource_id_param="workflow_id",
)
_wf_perm_update = PermissionChecker(
    "workflow",
    "update",
    resource_model=Workflow,
    resource_id_param="workflow_id",
)
_wf_perm_delete = PermissionChecker(
    "workflow",
    "delete",
    resource_model=Workflow,
    resource_id_param="workflow_id",
)
_wf_perm_create = PermissionChecker(
    "workflow",
    "create",
    body_project_field="project_id",
)

WORKFLOW_NOT_FOUND: str = "Workflow not found"


async def _populate_published_version_number(
    workflow_read: WorkflowRead, workflow: Workflow, version: WorkflowVersion, db: AsyncSession
) -> None:
    """Set published_version_number on a single WorkflowRead."""
    if workflow.published_version_id is None:
        return
    if version.id == workflow.published_version_id:
        workflow_read.published_version_number = version.version
    else:
        result = await db.exec(
            select(WorkflowVersion.version).where(WorkflowVersion.id == workflow.published_version_id)
        )
        workflow_read.published_version_number = result.one_or_none()


@overload
async def _build_workflow_with_version_response(
    workflow: Workflow,
    version: WorkflowVersion,
    service: WorkflowService,
) -> WorkflowReadWithVersion: ...


@overload
async def _build_workflow_with_version_response(
    workflow: Workflow,
    version: WorkflowVersion,
    service: WorkflowService,
    *,
    validation_result: "ValidationResult | None",
) -> WorkflowReadWithVersion: ...


@overload
async def _build_workflow_with_version_response(
    workflow: Workflow,
    version: WorkflowVersion,
    service: WorkflowService,
    *,
    warning: str,
) -> PublishWorkflowVersionResponse: ...


async def _build_workflow_with_version_response(
    workflow: Workflow,
    version: WorkflowVersion,
    service: WorkflowService,
    *,
    warning: str | None = None,
    validation_result: "ValidationResult | None" = None,
) -> WorkflowReadWithVersion | PublishWorkflowVersionResponse:
    workflow_read = WorkflowRead.model_validate(workflow, from_attributes=True)
    await _populate_published_version_number(workflow_read, workflow, version, service.session)
    ever_published, pub_ts = await service.get_publish_context([version.id])
    base = workflow_read.model_dump()
    base["version"] = deserialize_workflow_version(version, workflow.published_version_id, ever_published, pub_ts)
    if validation_result is not None and _has_validation_issues(validation_result):
        base["validation_result"] = validation_result.model_dump(mode="json")
    if warning is not None:
        base["warning"] = warning
        return PublishWorkflowVersionResponse.model_validate(base)
    return WorkflowReadWithVersion.model_validate(base)


def _definition_to_dict(wf_def: WorkflowDefinition | dict[str, Any]) -> dict[str, Any]:
    """Convert a WorkflowDefinition or raw dict to a plain dict for the service layer.

    Uses exclude_defaults=True to match the normalization in
    _create_version_record (change detection) and to strip None values
    that break the downstream JSON Schema validator (unevaluatedProperties).
    """
    if isinstance(wf_def, dict):
        return wf_def
    return wf_def.model_dump(exclude_defaults=True)


# ============================================================================
# Dependency Injection Providers
# ============================================================================


def get_workflow_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> WorkflowService:
    """Dependency provider for WorkflowService.

    FastAPI will call this function automatically, injecting all dependencies.
    This centralizes WorkflowService creation across all endpoints.
    """
    return WorkflowService(db, current_user, request.app.state.authz_evaluator)


def get_execution_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    temporal_service: Annotated[
        TemporalExecutionService | None,
        Depends(get_temporal_execution_service),
    ],
) -> ExecutionService:
    """Dependency provider for ExecutionService.

    FastAPI will call this function automatically, injecting all dependencies.
    """
    return ExecutionService(db, current_user, temporal_service=temporal_service)


# ============================================================================
# Workflow endpoints
# ============================================================================


_validate_router = SyntaraRouter(route_class=_ValidationRoute)


@_validate_router.post(
    "/validate",
    summary="Validate workflow definition",
    response_model=ValidationResult,
    dependencies=[NO_PERMISSION],
    operation_id="validate_workflow_definition",
    response_description="Validation result",
    responses={422: {"model": DetailedValidationProblemDetail, "description": "Unprocessable Content"}},
)
async def validate_workflow_definition(
    request: WorkflowValidateRequest,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
) -> ValidationResult:
    """Validate a workflow definition without saving it.

    Requires authentication but no specific workflow/project permission:
    validation is a stateless, side-effect-free check of caller-supplied
    data with no workflow_id or project_id in scope to authorize against.
    """
    system_cof = await get_system_continue_on_failure()
    result = workflow_validator.collect_findings(
        request.workflow_definition,
        system_continue_on_failure=system_cof,
    )
    if not result.is_valid:
        raise WorkflowDefinitionInvalidError(result)
    return result


router.include_router(_validate_router)


@router.post(
    "",
    summary="Create workflow",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_wf_perm_create)],
    operation_id="create_workflow",
    response_description="Workflow created",
)
async def create_workflow(
    request: WorkflowCreate,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRead:
    """Create a new workflow with initial version."""
    workflow, _, result = await service.create_workflow(
        name=request.name,
        description=request.description,
        labels=request.labels,
        workflow_definition=_definition_to_dict(request.workflow_definition),
        project_id=request.project_id,
        is_import=request.is_import,
    )
    read = WorkflowRead.model_validate(workflow, from_attributes=True)
    if _has_validation_issues(result):
        read.validation_result = result
    return read


@router.get(
    "",
    summary="List workflows",
    operation_id="list_workflows",
    response_description="List of workflows",
)
async def list_workflows(
    request: Request,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    params: Annotated[WorkflowListParams, Query()],
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("workflow", "read"))],
) -> WorkflowListResponse:
    """List workflows the current user has read access to.

    Supports filtering using query parameters with standard operators:
    - created_by: Filter by creator user ID (created_by=uuid)
    - is_enabled: Filter by enabled status (is_enabled=true|false)
    - labels: Filter by labels using bracket notation (labels[environment]=production)

    Uses cursor-based pagination for scalability and consistency.
    """
    result = await service.list_workflows_cursor(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=visibility.to_allowed_projects(),
    )
    await service.populate_published_version_numbers(result.resources)
    return result


@router.get(
    "/{workflow_id}",
    summary="Get workflow",
    dependencies=[Depends(_wf_perm_read)],
    operation_id="get_workflow",
    response_description="Workflow details",
)
async def get_workflow(
    workflow_id: UUID,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowReadWithVersion:
    """Get a workflow by ID including its current active version."""
    workflow, current_version = await service.get_workflow_with_version(workflow_id)
    return await _build_workflow_with_version_response(workflow, current_version, service)


@router.patch(
    "/{workflow_id}",
    summary="Update workflow",
    dependencies=[Depends(_wf_perm_update)],
    operation_id="update_workflow",
    response_description="Updated workflow",
)
async def update_workflow(
    workflow_id: UUID,
    request: WorkflowUpdate,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowReadWithVersion:
    """Update workflow.

    Supports both metadata-only updates and workflow definition updates:
    - Metadata only (name, description, labels): Updates without creating new version
    - With workflow_definition: Validates definition, compares with current version, creates new WorkflowVersion
      only if definition differs (change detection optimization)
    """
    workflow, current_version, validation_result = await service.update_workflow(
        workflow_id=workflow_id,
        name=request.name,
        description=request.description,
        labels=request.labels,
        project_id=request.project_id,
        workflow_definition=_definition_to_dict(request.workflow_definition)
        if request.workflow_definition is not None
        else None,
        change_description=request.change_description,
        expected_version=request.expected_version,
    )
    return await _build_workflow_with_version_response(
        workflow, current_version, service, validation_result=validation_result
    )


@router.delete(
    "/{workflow_id}",
    summary="Delete workflow",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_wf_perm_delete)],
    operation_id="delete_workflow",
    response_description="Workflow deleted",
)
async def delete_workflow(
    workflow_id: UUID,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> None:
    """Soft delete a workflow."""
    await service.delete_workflow(workflow_id)


@router.post(
    "/{workflow_id}/test",
    response_model=ExecutionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_wf_perm_update)],
    operation_id="test_workflow_node",
    summary="Test a single node in a workflow",
    response_description="Test execution created",
)
async def test_workflow_node(
    workflow_id: UUID,
    request: TestExecutionCreate,
    execution_service: Annotated[ExecutionService, Depends(get_execution_service)],
) -> ExecutionRead:
    """Test a single node in a workflow with mocked predecessor outputs."""
    return await execution_service.create_test_execution(
        workflow_id=workflow_id,
        target_node_id=request.target_node_id,
        pre_resolved_nodes=request.pre_resolved_nodes,
        trigger_inputs=request.trigger_inputs,
        execute_target=request.execute_target,
        trigger_node_id=request.trigger_node_id,
    )


# ============================================================================
# Workflow version endpoints
# ----------------------------------------------------------------------------
# NOTE: WorkflowVersion entities are READ-ONLY and system-managed.
# Versions are created automatically via PATCH /workflows/{id} with workflow_definition.
# No POST endpoint for manual version creation - this ensures version integrity.
# ============================================================================


@router.get(
    "/{workflow_id}/versions",
    summary="List workflow versions",
    dependencies=[Depends(_wf_perm_read)],
    operation_id="list_workflow_versions",
    response_description="Workflow version history",
)
async def list_workflow_versions(
    workflow_id: UUID,
    request: Request,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    params: Annotated[WorkflowVersionListParams, Query()],
) -> WorkflowVersionListResponse:
    """List versions for a workflow with cursor-based pagination."""
    return await service.list_workflow_versions_cursor(
        workflow_id=workflow_id,
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
    )


@router.get(
    "/{workflow_id}/versions/{version}",
    summary="Get workflow version",
    dependencies=[Depends(_wf_perm_read)],
    operation_id="get_workflow_version",
    response_description="Workflow version details",
)
async def get_workflow_version(
    workflow_id: UUID,
    version: int,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowVersionRead:
    """Get a specific workflow version."""
    db = service.session
    workflow_result = await db.exec(
        select(Workflow).filter(Workflow.id == workflow_id, Workflow.deleted_at.is_(None))  # type: ignore[arg-type,union-attr]
    )
    workflow = workflow_result.one_or_none()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=WORKFLOW_NOT_FOUND,
        )

    result = await db.exec(
        select(WorkflowVersion).filter(
            WorkflowVersion.workflow_id == workflow_id,  # type: ignore[arg-type]
            WorkflowVersion.version == version,  # type: ignore[arg-type]
            WorkflowVersion.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    workflow_version = result.one_or_none()

    if not workflow_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version} not found for this workflow",
        )

    ever_published, pub_ts = await service.get_publish_context([workflow_version.id])

    return WorkflowVersionRead.model_validate(
        deserialize_workflow_version(workflow_version, workflow.published_version_id, ever_published, pub_ts)
    )


@router.post(
    "/{workflow_id}/versions/{version}/publish",
    summary="Publish workflow version",
    response_model=PublishWorkflowVersionResponse,
    dependencies=[Depends(_wf_perm_update)],
    operation_id="publish_workflow_version",
    response_description="Published workflow version",
)
async def publish_workflow_version(
    workflow_id: UUID,
    version: int,
    request: PublishVersionRequest,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> PublishWorkflowVersionResponse:
    """Publish a specific workflow version."""
    workflow, published_version, warning = await service.publish_workflow_version(
        workflow_id=workflow_id,
        version=version,
        name=request.name,
        change_description=request.change_description,
        workflow_definition=_definition_to_dict(request.workflow_definition)
        if request.workflow_definition is not None
        else None,
        expected_version=request.expected_version,
    )
    return await _build_workflow_with_version_response(workflow, published_version, service, warning=warning)


@router.post(
    "/{workflow_id}/unpublish",
    summary="Unpublish workflow",
    dependencies=[Depends(_wf_perm_update)],
    operation_id="unpublish_workflow",
    response_description="Unpublished workflow",
)
async def unpublish_workflow(
    workflow_id: UUID,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRead:
    """Unpublish the currently published workflow version."""
    workflow = await service.unpublish_workflow(workflow_id=workflow_id)
    return WorkflowRead.model_validate(workflow)


@router.post(
    "/{workflow_id}/versions/{version}/restore",
    summary="Restore workflow version",
    dependencies=[Depends(_wf_perm_update)],
    operation_id="restore_workflow_version",
    response_description="Restored workflow version",
)
async def restore_workflow_version(
    workflow_id: UUID,
    version: int,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowReadWithVersion:
    """Restore a previous workflow version as a new draft."""
    workflow, restored_version = await service.restore_workflow_version(
        workflow_id=workflow_id,
        version=version,
    )
    return await _build_workflow_with_version_response(workflow, restored_version, service)


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    safe = re.sub(r"[^\w\-.]", "_", name, flags=re.ASCII)
    return safe[:200] or "workflow"


@router.get(
    "/{workflow_id}/versions/{version}/export",
    summary="Export workflow version",
    dependencies=[Depends(_wf_perm_read)],
    operation_id="export_workflow_version",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"application/json": {}}, "description": "Workflow version definition as JSON file"},
        404: {"description": WORKFLOW_NOT_FOUND},
    },
)
async def export_workflow_version(
    workflow_id: UUID,
    version: int,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> StreamingResponse:
    """Export a workflow version definition as a downloadable JSON file."""
    workflow, version_record = await service.get_version_for_export(
        workflow_id=workflow_id,
        version=version,
    )

    safe_name = _sanitize_filename(workflow.name)
    filename = f"{safe_name}-v{version}.json"
    content = json.dumps(version_record.workflow_definition, indent=2)

    return StreamingResponse(
        BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


@router.patch(
    "/{workflow_id}/versions/{version}",
    summary="Update workflow version metadata",
    dependencies=[Depends(_wf_perm_update)],
    operation_id="update_workflow_version_metadata",
    response_description="Updated workflow version",
    responses={
        404: {"description": WORKFLOW_NOT_FOUND},
    },
)
async def update_workflow_version_metadata(
    workflow_id: UUID,
    version: int,
    request: WorkflowVersionUpdate,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowVersionRead:
    """Update a workflow version's metadata (name, change_description)."""
    workflow = await service.get_workflow_by_id(workflow_id)
    updated = await service.update_version_metadata(
        workflow_id=workflow_id,
        version=version,
        name=request.name,
        change_description=request.change_description,
        fields_set=request.model_fields_set,
    )
    ever_published, pub_ts = await service.get_publish_context([updated.id])
    return WorkflowVersionRead.model_validate(
        deserialize_workflow_version(updated, workflow.published_version_id, ever_published, pub_ts)
    )
