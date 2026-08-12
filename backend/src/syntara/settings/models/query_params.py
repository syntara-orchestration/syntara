"""Query parameter models for settings list endpoints."""

from sqlmodel import Field

from syntara.core.models.base import BaseListParams


class SettingsListParams(BaseListParams):
    """Query parameters for the settings list endpoint."""

    category: str | None = Field(default=None, description="Filter by category slug (e.g. 'context_manager')")
    group: str | None = Field(default=None, description="Filter by group name (e.g. 'Token limits')")
