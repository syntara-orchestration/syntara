"""Settings REST API endpoints."""

import re
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.syntara_router import SyntaraRouter
from syntara.settings.models.api_models import (
    CategoriesListResponse,
    RuntimeSettingRead,
    SettingBulkUpdateRequest,
    SettingsListResponse,
    SettingUpdate,
)
from syntara.settings.models.query_params import SettingsListParams
from syntara.settings.services.settings_service import SettingsService

router = SyntaraRouter(prefix="/settings", tags=["Settings"])


# ============================================================================
# Dependency Injection Providers
# ============================================================================


def get_settings_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SettingsService:
    """Dependency provider for SettingsService."""
    return SettingsService(db, current_user)


_require_settings_read = PermissionChecker("setting", "read")
_require_settings_write = PermissionChecker("setting", "write")


_SETTING_KEY_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$")


def _validate_key(key: str) -> None:
    """Validate that a setting key matches the dot-namespaced format."""
    if not _SETTING_KEY_PATTERN.match(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid setting key format: '{key}'",
        )


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    summary="List settings",
    dependencies=[Depends(_require_settings_read)],
    operation_id="list_settings",
    response_description="Paginated list of runtime settings",
)
async def list_settings(
    request: Request,
    service: Annotated[SettingsService, Depends(get_settings_service)],
    params: Annotated[SettingsListParams, Depends()],
) -> SettingsListResponse:
    """List all runtime settings with pagination, filtering, and sorting."""
    return await service.list_settings(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
    )


@router.get(
    "/categories",
    summary="List categories",
    dependencies=[Depends(_require_settings_read)],
    operation_id="list_categories",
    response_description="List of setting categories",
)
async def list_categories(
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> CategoriesListResponse:
    """List all setting categories with their group names."""
    return await service.list_categories()


@router.get(
    "/{key}",
    summary="Get setting",
    dependencies=[Depends(_require_settings_read)],
    operation_id="get_setting",
    response_description="Setting details",
)
async def get_setting(
    key: str,
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> RuntimeSettingRead:
    """Get a single runtime setting by its dot-namespaced key."""
    _validate_key(key)
    return await service.get(key)


@router.patch(
    "/{key}",
    summary="Update setting",
    dependencies=[Depends(_require_settings_write)],
    operation_id="update_setting",
    response_description="Setting updated",
)
async def update_setting(
    key: str,
    body: SettingUpdate,
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> RuntimeSettingRead:
    """Update a runtime setting value with optimistic locking."""
    _validate_key(key)
    return await service.update(
        key=key,
        value=body.value,
        expected_version=body.expected_version,
    )


@router.patch(
    "",
    summary="Bulk update settings",
    dependencies=[Depends(_require_settings_write)],
    operation_id="bulk_update_settings",
    response_description="All settings updated successfully",
)
async def bulk_update_settings(
    body: SettingBulkUpdateRequest,
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> SettingsListResponse:
    """Update multiple settings in a single request."""
    seen_keys: set[str] = set()
    for item in body.updates:
        _validate_key(item.key)
        if item.key in seen_keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate key in bulk update: '{item.key}'",
            )
        seen_keys.add(item.key)
    updated = await service.bulk_update(body.updates)
    return SettingsListResponse(resources=updated, next=None, prev=None, total=None)
