"""AAP proxy router — auto-discovered under /api/v1/proxies/aap.

Thin layer that validates query params, resolves dependencies,
and delegates to AAPProxyService.

Authentication: Endpoints accept optional ``credential_id`` and
``integration_id`` query parameters. When both are omitted, the proxy uses
the unique visible enabled AAP integration and its management credential.
When more than one AAP integration is visible, pass ``integration_id`` to
select one; ``credential_id`` may still be omitted (management credential is
used). When ``credential_id`` is provided, the specified Syntara credential
(type: "Ansible Automation Platform") is decrypted and used instead; callers
may only use credentials they own.

Authorization: The ``current_user`` dependency ensures only authenticated
Syntara users can call these endpoints. When using credential_id, users can
only use credentials they own (authorization check enforced). When using
integration_id, project-scoped integration visibility is enforced via
``ProjectScopeFilter("integration", "read")``.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Path
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.aap.audit.aap_resource_access import (
    AAPAccessAction,
    AAPResourceAccessEvent,
    AAPResourceType,
)
from syntara.aap.models.queries import AAPBaseQuery, AAPResourceQuery
from syntara.aap.models.responses import (
    AAPCredential,
    AAPExecutionEnvironment,
    AAPInstanceGroup,
    AAPInventory,
    AAPJobTemplate,
    AAPJobTemplateDetail,
    AAPLabel,
    AAPListResponse,
    AAPOrganization,
    AAPWorkflowJobTemplate,
    AAPWorkflowJobTemplateDetail,
)
from syntara.aap.services.aap_proxy_service import AAPProxyService
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.auth import get_current_user
from syntara.authz.dependencies import ProjectScopeFilter
from syntara.authz.engine import AllowedProjectsResult
from syntara.core.config.base import Settings, get_settings
from syntara.core.database.session import get_db
from syntara.core.models import User

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/proxies/aap", tags=["Ansible Automation Platform Proxy"])

_integration_scope = ProjectScopeFilter("integration", "read")


def _credential_used_for_audit(error_type: str | None) -> bool:
    """Whether an Orchestrator credential was resolved for this proxy request.

    True on success and after decrypt (auth/upstream errors). False when the
    request failed before decrypt (no/ambiguous integration, missing
    management credential). Env-var auth is not used on this path.
    """
    return error_type != "AAPNotConfiguredError"


# ============================================================================
# Dependency Injection
# ============================================================================


async def _get_aap_proxy_service(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
    allowed_projects: Annotated[AllowedProjectsResult, Depends(_integration_scope)],
) -> AsyncGenerator[AAPProxyService]:
    """Provide AAPProxyService with settings and db session wired; close client after request."""
    service = AAPProxyService(settings, db, allowed_projects=allowed_projects)
    try:
        yield service
    finally:
        await service.close()


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/organizations", summary="List organizations", operation_id="list_aap_organizations")
async def list_organizations(
    query: Annotated[AAPBaseQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPListResponse[AAPOrganization]:
    """List Ansible Automation Platform organizations."""
    error_type = None
    result_count = None
    try:
        result = await service.list_organizations(query, user_id=current_user.id)
        result_count = result.count
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.ORGANIZATIONS,
                action=AAPAccessAction.LIST,
                user_id=current_user.id,
                username=current_user.username,
                result_count=result_count,
                credential_used=_credential_used_for_audit(error_type),
                search_filter=query.search,
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get("/job_templates", summary="List job templates", operation_id="list_aap_job_templates")
async def list_job_templates(
    query: Annotated[AAPResourceQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPListResponse[AAPJobTemplate]:
    """List Ansible Automation Platform job templates, optionally filtered by organization."""
    error_type = None
    result_count = None
    try:
        result = await service.list_job_templates(query, user_id=current_user.id)
        result_count = result.count
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.JOB_TEMPLATES,
                action=AAPAccessAction.LIST,
                user_id=current_user.id,
                username=current_user.username,
                result_count=result_count,
                credential_used=_credential_used_for_audit(error_type),
                search_filter=query.search,
                organization_filter=query.organization,
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get("/job_templates/{job_template_id}", summary="Get job template", operation_id="get_aap_job_template")
async def get_job_template(
    job_template_id: Annotated[int, Path(ge=1)],
    query: Annotated[AAPBaseQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPJobTemplateDetail:
    """Get Ansible Automation Platform job template details including prompt-on-launch capabilities."""
    credential_id_str = str(query.credential_id) if query.credential_id else None
    error_type = None
    resource_name = None
    try:
        integration_id_str = str(query.integration_id) if query.integration_id else None
        result = await service.get_job_template(
            job_template_id,
            credential_id=credential_id_str,
            user_id=current_user.id,
            integration_id=integration_id_str,
        )
        resource_name = result.name
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.JOB_TEMPLATES,
                action=AAPAccessAction.GET,
                user_id=current_user.id,
                username=current_user.username,
                resource_id=job_template_id,
                resource_name=resource_name,
                credential_used=_credential_used_for_audit(error_type),
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get(
    "/workflow_job_templates", summary="List workflow job templates", operation_id="list_aap_workflow_job_templates"
)
async def list_workflow_job_templates(
    query: Annotated[AAPResourceQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPListResponse[AAPWorkflowJobTemplate]:
    """List Ansible Automation Platform workflow job templates, optionally filtered by organization."""
    error_type = None
    result_count = None
    try:
        result = await service.list_workflow_job_templates(query, user_id=current_user.id)
        result_count = result.count
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.WORKFLOW_JOB_TEMPLATES,
                action=AAPAccessAction.LIST,
                user_id=current_user.id,
                username=current_user.username,
                result_count=result_count,
                credential_used=_credential_used_for_audit(error_type),
                search_filter=query.search,
                organization_filter=query.organization,
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get(
    "/workflow_job_templates/{workflow_job_template_id}",
    summary="Get workflow job template",
    operation_id="get_aap_workflow_job_template",
)
async def get_workflow_job_template(
    workflow_job_template_id: Annotated[int, Path(ge=1)],
    query: Annotated[AAPBaseQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPWorkflowJobTemplateDetail:
    """Get Ansible Automation Platform workflow job template details including prompt-on-launch capabilities."""
    credential_id_str = str(query.credential_id) if query.credential_id else None
    error_type = None
    resource_name = None
    try:
        integration_id_str = str(query.integration_id) if query.integration_id else None
        result = await service.get_workflow_job_template(
            workflow_job_template_id,
            credential_id=credential_id_str,
            user_id=current_user.id,
            integration_id=integration_id_str,
        )
        resource_name = result.name
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.WORKFLOW_JOB_TEMPLATES,
                action=AAPAccessAction.GET,
                user_id=current_user.id,
                username=current_user.username,
                resource_id=workflow_job_template_id,
                resource_name=resource_name,
                credential_used=_credential_used_for_audit(error_type),
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get("/inventories", summary="List inventories", operation_id="list_aap_inventories")
async def list_inventories(
    query: Annotated[AAPResourceQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPListResponse[AAPInventory]:
    """List Ansible Automation Platform inventories, optionally filtered by organization."""
    error_type = None
    result_count = None
    try:
        result = await service.list_inventories(query, user_id=current_user.id)
        result_count = result.count
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.INVENTORIES,
                action=AAPAccessAction.LIST,
                user_id=current_user.id,
                username=current_user.username,
                result_count=result_count,
                credential_used=_credential_used_for_audit(error_type),
                search_filter=query.search,
                organization_filter=query.organization,
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get(
    "/execution_environments", summary="List execution environments", operation_id="list_aap_execution_environments"
)
async def list_execution_environments(
    query: Annotated[AAPResourceQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPListResponse[AAPExecutionEnvironment]:
    """List Ansible Automation Platform execution environments, optionally filtered by organization."""
    error_type = None
    result_count = None
    try:
        result = await service.list_execution_environments(query, user_id=current_user.id)
        result_count = result.count
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.EXECUTION_ENVIRONMENTS,
                action=AAPAccessAction.LIST,
                user_id=current_user.id,
                username=current_user.username,
                result_count=result_count,
                credential_used=_credential_used_for_audit(error_type),
                search_filter=query.search,
                organization_filter=query.organization,
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get("/credentials", summary="List AAP credentials", operation_id="list_aap_credentials")
async def list_credentials(
    query: Annotated[AAPBaseQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPListResponse[AAPCredential]:
    """List Ansible Automation Platform credentials (not organization-scoped)."""
    error_type = None
    result_count = None
    try:
        result = await service.list_credentials(query, user_id=current_user.id)
        result_count = result.count
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.CREDENTIALS,
                action=AAPAccessAction.LIST,
                user_id=current_user.id,
                username=current_user.username,
                result_count=result_count,
                credential_used=_credential_used_for_audit(error_type),
                search_filter=query.search,
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get("/instance_groups", summary="List instance groups", operation_id="list_aap_instance_groups")
async def list_instance_groups(
    query: Annotated[AAPBaseQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPListResponse[AAPInstanceGroup]:
    """List Ansible Automation Platform instance groups (not organization-scoped)."""
    error_type = None
    result_count = None
    try:
        result = await service.list_instance_groups(query, user_id=current_user.id)
        result_count = result.count
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.INSTANCE_GROUPS,
                action=AAPAccessAction.LIST,
                user_id=current_user.id,
                username=current_user.username,
                result_count=result_count,
                credential_used=_credential_used_for_audit(error_type),
                search_filter=query.search,
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result


@router.get("/labels", summary="List labels", operation_id="list_aap_labels")
async def list_labels(
    query: Annotated[AAPBaseQuery, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AAPProxyService, Depends(_get_aap_proxy_service)],
) -> AAPListResponse[AAPLabel]:
    """List Ansible Automation Platform labels."""
    error_type = None
    result_count = None
    try:
        result = await service.list_labels(query, user_id=current_user.id)
        result_count = result.count
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            AAPResourceAccessEvent(
                resource_type=AAPResourceType.LABELS,
                action=AAPAccessAction.LIST,
                user_id=current_user.id,
                username=current_user.username,
                result_count=result_count,
                credential_used=_credential_used_for_audit(error_type),
                search_filter=query.search,
                error_type=error_type,
                principal_type=current_user.__dict__.get("__principal_type__"),
            )
        )
    return result
