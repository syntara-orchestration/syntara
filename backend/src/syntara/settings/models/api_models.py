"""Request and response schemas for the settings REST API."""

from __future__ import annotations

from typing import Any

from sqlmodel import Field, SQLModel

from syntara.core.models.base import BaseResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.settings.models.runtime_setting import SettingValueType  # noqa: TC001 - used at runtime by SQLModel


class RuntimeSettingRead(BaseResource):
    """Read schema for a single runtime setting."""

    key: str
    name: str
    description: str | None
    helper_text: str | None
    depends_on: str | None
    category: str
    group: str | None
    value: Any
    default_value: Any
    effective_value: Any
    value_type: SettingValueType
    requires_restart: bool
    cache_ttl_seconds: int | None
    validation_schema: dict[str, Any] | None
    version: int


class SettingsListResponse(ResourcesResponse[RuntimeSettingRead]):
    """Paginated list response for runtime settings."""


class SettingUpdate(SQLModel):
    """Request body for PATCH /settings/{key}."""

    value: Any
    expected_version: int | None = None


class SettingBulkUpdateItem(SQLModel):
    """A single setting update within a bulk request."""

    key: str
    value: Any
    expected_version: int | None = None


_MAX_BULK_UPDATE_ITEMS = 500


class SettingBulkUpdateRequest(SQLModel):
    """Request body for PATCH /settings (bulk update)."""

    updates: list[SettingBulkUpdateItem] = Field(..., max_length=_MAX_BULK_UPDATE_ITEMS)


class SettingCategoryRead(SQLModel):
    """Read schema for a setting category."""

    slug: str
    name: str
    description: str | None
    display_order: int = 0
    group_names: list[str]


class CategoriesListResponse(SQLModel):
    """Response schema for listing setting categories."""

    resources: list[SettingCategoryRead]
