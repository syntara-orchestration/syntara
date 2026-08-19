"""Query parameter models for credential list endpoints."""

from typing import Literal

from sqlmodel import Field

from syntara.core.models.base import BaseListParams


class CredentialListParams(BaseListParams):
    """Query parameters for listing credentials."""

    for_action: Literal["use"] | None = Field(default=None, description="When 'use', returns only usable credentials.")
