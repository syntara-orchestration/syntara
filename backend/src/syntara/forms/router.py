"""Forms API router for form prompt management and workflow integration."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import VisibilityResult
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.syntara_router import SyntaraRouter
from syntara.forms.models.api_models import (
    BatchFormPromptRequest,
    BatchUpdateResponse,
    FormPromptCreateRequest,
    FormPromptSubmitRequest,
    FormPromptSummary,
)
from syntara.forms.models.form_prompt import FormPrompt, FormPromptListResponse, FormPromptRead
from syntara.forms.services.form_prompt_service import FormPromptService

router = SyntaraRouter(prefix="/form_prompts", tags=["Form Prompts"])

_form_prompt_perm_read = PermissionChecker(
    "form_prompt",
    "read",
    resource_model=FormPrompt,
    resource_id_param="form_prompt_id",
)
_form_prompt_perm_submit = PermissionChecker(
    "form_prompt",
    "submit",
    resource_model=FormPrompt,
    resource_id_param="form_prompt_id",
)


def get_form_prompt_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> FormPromptService:
    """Dependency to get FormPromptService instance."""
    return FormPromptService(session=session, user=user)


# Service-to-service endpoint (Temporal worker creates form prompts).
# Production: mTLS-authenticated service principals bypass permission checks.
# Local dev: falls back to admin-only when s2s_tls_enabled=false.
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker("form_prompt", "create"))],
    operation_id="create_form_prompt",
    summary="Create form prompt",
    description="Create a new form prompt. Internal service-to-service endpoint for workflow engine.",
    response_description="Form prompt created",
)
async def create_form_prompt(
    request: FormPromptCreateRequest,
    service: Annotated[FormPromptService, Depends(get_form_prompt_service)],
) -> FormPromptSummary:
    """Create a new form prompt."""
    return await service.create(request)


@router.get(
    "",
    operation_id="list_form_prompts",
    summary="List form prompts",
    description="""List form prompts with filtering, sorting, and pagination.

Supports filtering using query parameters with standard operators:
- status: Filter by form prompt status (status=pending)
- execution_id: Filter by parent execution ID (execution_id=uuid)
- prompt_node_id: Filter by node ID (prompt_node_id=form1)

Uses cursor-based pagination for scalability and consistency.""",
    response_description="List of form prompts",
)
async def list_form_prompts(
    request: Request,
    service: Annotated[FormPromptService, Depends(get_form_prompt_service)],
    params: Annotated[BaseListParams, Depends()],
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("form_prompt", "read"))],
) -> FormPromptListResponse:
    """List form prompts with filtering, sorting, and pagination.

    Supports filtering using query parameters with standard operators:
    - status: Filter by form prompt status (status=pending)
    - execution_id: Filter by parent execution ID (execution_id=uuid)
    - prompt_node_id: Filter by node ID (prompt_node_id=form1)

    Uses cursor-based pagination for scalability and consistency.

    """
    return await service.list(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=visibility.to_allowed_projects(),
    )


@router.post(
    "/batch",
    dependencies=[Depends(PermissionChecker("form_prompt", "create"))],
    operation_id="batch_update_form_prompts",
    summary="Batch update form prompt statuses",
    description="Batch update form prompt statuses. Internal endpoint for expire/cancel activities.",
    response_description="Batch update results",
)
async def batch_update_form_prompts(
    request: BatchFormPromptRequest,
    service: Annotated[FormPromptService, Depends(get_form_prompt_service)],
) -> BatchUpdateResponse:
    """Batch update form prompt statuses."""
    return await service.batch_update_status(request)


@router.get(
    "/{form_prompt_id}",
    dependencies=[Depends(_form_prompt_perm_read)],
    operation_id="get_form_prompt",
    summary="Get form prompt request",
    response_description="Form prompt request details",
)
async def get_form_prompt(
    form_prompt_id: UUID,
    service: Annotated[FormPromptService, Depends(get_form_prompt_service)],
) -> FormPromptRead:
    """Get a form prompt by ID, including its form definition and responder configuration."""
    return await service.get(form_prompt_id)


@router.post(
    "/{form_prompt_id}/submit",
    dependencies=[Depends(_form_prompt_perm_submit)],
    operation_id="submit_form_prompt",
    summary="Submit a response to a form prompt",
    response_description="Updated form prompt with the submitted response",
)
async def submit_form_prompt(
    form_prompt_id: UUID,
    request: FormPromptSubmitRequest,
    service: Annotated[FormPromptService, Depends(get_form_prompt_service)],
) -> FormPromptRead:
    """Submit a response to a pending form prompt and resume its workflow."""
    return await service.submit(form_prompt_id, request.response_data)
