"""Forms API router.

Minimal internal-facing implementation for workflow engine integration.
AAP-91889 will extend with full filtering/sorting/enrichment and user-facing endpoints.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from syntara.authz.dependencies import PermissionChecker
from syntara.core.database.session import get_db
from syntara.core.syntara_router import SyntaraRouter
from syntara.forms.models.api_models import (
    BatchFormPromptRequest,
    BatchUpdateResponse,
    FormPromptCreateRequest,
    FormPromptStatus,
    FormPromptSummary,
)
from syntara.forms.models.form_prompt import FormPromptListResponse
from syntara.forms.services.form_prompt_service import FormPromptService

router = SyntaraRouter(prefix="/form_prompts", tags=["Form Prompts"])


def get_form_prompt_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FormPromptService:
    """Dependency to get FormPromptService instance."""
    return FormPromptService(session=session)


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


# Minimal internal-facing implementation. AAP-91889 will extend with full filtering/sorting.
@router.get(
    "",
    dependencies=[Depends(PermissionChecker("form_prompt", "read"))],
    operation_id="list_form_prompts",
    summary="List form prompts",
    description="List form prompts filtered by execution ID. Internal endpoint for expire/cancel activities.",
    response_description="List of form prompts",
)
async def list_form_prompts(
    execution_id: UUID,
    service: Annotated[FormPromptService, Depends(get_form_prompt_service)],
    status: FormPromptStatus | None = None,
) -> FormPromptListResponse:
    """List form prompts for an execution."""
    return await service.list_by_execution(execution_id=execution_id, status=status)


# Minimal internal-facing implementation. AAP-91889 will extend with full batch operations.
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
