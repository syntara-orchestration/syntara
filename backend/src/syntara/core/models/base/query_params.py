"""Base query parameter models for FastAPI endpoints.

This module defines SQLModel-based models for query parameters used across the API endpoints.
Using Query Parameter Models provides better validation, documentation, and reusability.
"""

from typing import Annotated

from pydantic import StringConstraints
from sqlmodel import Field, SQLModel

_SORT_PATTERN = r"^-?[a-z][a-z0-9_]*$"


class BaseListParams(SQLModel):
    """Base query parameters for list endpoints with pagination and sorting."""

    limit: int = Field(default=20, gt=0, le=100, description="Maximum number of results per page")
    cursor: str | None = Field(default=None, description="Pagination cursor from previous response")
    sort: Annotated[str, StringConstraints(pattern=_SORT_PATTERN)] | None = Field(
        default=None, description="Sort parameter (e.g., 'name', '-created_at')"
    )
    include_total: bool = Field(default=False, description="Include total count in response (expensive)")


class BasePaginatedRequest(SQLModel):
    """Base request body for POST endpoints that return paginated lists.

    POST endpoints that return paginated results should inherit from this class
    to get standard pagination fields in the request body. For GET endpoints,
    use BaseListParams with Query() instead.
    """

    limit: int = Field(default=20, gt=0, le=100, description="Maximum number of results per page")
    cursor: str | None = Field(default=None, description="Pagination cursor from previous response")
    sort: Annotated[str, StringConstraints(pattern=_SORT_PATTERN)] | None = Field(
        default=None, description="Sort parameter (e.g., 'name', '-created_at')"
    )
    include_total: bool = Field(default=False, description="Include total count in response (expensive)")
