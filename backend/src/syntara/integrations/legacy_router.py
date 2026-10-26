"""Compatible v1 routes sharing business logic and permissions with v2."""

from copy import copy
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request, status
from fastapi.routing import APIRoute

from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import AllowedProjectsResult
from syntara.core.syntara_router import SyntaraRouter
from syntara.integrations import router as current
from syntara.integrations.adapters.protocol import DiscoverResult
from syntara.integrations.models.integration import IntegrationCreate, IntegrationTestConnection, IntegrationUpdate
from syntara.integrations.models.legacy_integration import (
    IntegrationCreateV1,
    IntegrationListParamsV1,
    IntegrationListResponseV1,
    IntegrationReadV1,
    IntegrationTestConnectionV1,
    IntegrationUpdateV1,
)
from syntara.integrations.models.query_params import IntegrationListParams
from syntara.integrations.services.integration_service import IntegrationService

router = SyntaraRouter(tags=["Integrations"])
router.openapi_spec_name = "openapi"
Service = Annotated[IntegrationService, Depends(current.get_integration_service)]
Visibility = Annotated[AllowedProjectsResult, Depends(current.integration_read_visibility)]


@router.post(
    "/integrations",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker("integration", "create"))],
    operation_id="create_integration",
)
async def create_integration(data: IntegrationCreateV1, service: Service) -> IntegrationReadV1:
    """Create an integration using the original v1 input shape."""
    return IntegrationReadV1.model_validate(
        await current.create_integration(IntegrationCreate.model_validate(data.model_dump()), service)
    )


@router.get(
    "/integrations",
    dependencies=[
        Depends(VisibilityFilter("integration", "read")),
        Depends(VisibilityFilter("integration", "read-all")),
    ],
    operation_id="list_integrations",
)
async def list_integrations(
    request: Request,
    service: Service,
    params: Annotated[IntegrationListParamsV1, Query()],
    allowed_projects: Visibility,
) -> IntegrationListResponseV1:
    """List only integrations understood by v1 clients."""
    return IntegrationListResponseV1.model_validate(
        (
            await current.list_integrations(
                request, service, IntegrationListParams.model_validate(params.model_dump()), allowed_projects
            )
        ).model_dump()
    )


@router.get(
    "/integrations/{integration_id}",
    dependencies=[
        Depends(VisibilityFilter("integration", "read")),
        Depends(VisibilityFilter("integration", "read-all")),
    ],
    operation_id="get_integration",
)
async def get_integration(integration_id: UUID, service: Service, allowed_projects: Visibility) -> IntegrationReadV1:
    """Read a v1 integration; Kafka IDs are hidden."""
    return IntegrationReadV1.model_validate(await current.get_integration(integration_id, service, allowed_projects))


@router.patch(
    "/integrations/{integration_id}",
    dependencies=[Depends(PermissionChecker("integration", "update"))],
    operation_id="update_integration",
)
async def update_integration(integration_id: UUID, data: IntegrationUpdateV1, service: Service) -> IntegrationReadV1:
    """Update an integration using the original v1 configuration union."""
    return IntegrationReadV1.model_validate(
        await current.update_integration(
            integration_id, IntegrationUpdate.model_validate(data.model_dump(exclude_unset=True)), service
        )
    )


@router.post(
    "/integrations/discover",
    dependencies=[Depends(PermissionChecker("integration", "discover"))],
    operation_id="discover_integration_connection",
)
async def discover_integration_connection(data: IntegrationTestConnectionV1, service: Service) -> DiscoverResult:
    """Discover resources using the original v1 integration types."""
    return await current.discover_integration_connection(
        IntegrationTestConnection.model_validate(data.model_dump()), service
    )


# Remaining endpoints return no integration union. Reuse their RBAC and audit
# dependencies; the request-scoped v1 service hides Kafka before any operation.
_replaced = {
    "create_integration",
    "list_integrations",
    "get_integration",
    "update_integration",
    "discover_integration_connection",
}
# Keep v1 operation metadata identical while sharing endpoint behavior.
for legacy_route in router.routes:
    if isinstance(legacy_route, APIRoute):
        versioned_route = next(
            route
            for route in current.router.routes
            if isinstance(route, APIRoute) and route.operation_id == f"v2_{legacy_route.operation_id}"
        )
        legacy_route.summary = versioned_route.summary
        legacy_route.description = versioned_route.description

for original in current.router.routes:
    if (
        isinstance(original, APIRoute)
        and original.operation_id is not None
        and original.operation_id.removeprefix("v2_") not in _replaced
    ):
        route = copy(original)
        route.operation_id = original.operation_id.removeprefix("v2_")
        router.routes.append(route)
