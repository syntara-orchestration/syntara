"""Pagination response model definitions.

This module contains Pydantic classes for cursor-based pagination responses.
"""

from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from syntara.core.constants import FieldLimits

T = TypeVar("T")


class ResourcesResponseBase(BaseModel):
    """Base pagination metadata SQLModel for list responses.

    This model provides the common pagination metadata fields used in
    all paginated API responses.

    Attributes:
        next: Optional URI for the next page of results
        prev: Optional URI for the previous page of results
        total: Optional total count of resources (when include_total=true)

    """

    next: str | None = Field(default=None, description="Cursor for next page of results")

    prev: str | None = Field(default=None, description="Cursor for previous page of results")

    total: int | None = Field(default=None, ge=0, description="Total count of resources (only when include_total=true)")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        json_schema_extra={
            "examples": [
                {"next": "eyJpZCI6InV1aWQifQ", "prev": None, "total": 150},
                {"next": "eyJpZCI6Im5leHQifQ", "prev": "eyJpZCI6InByZXYifQ", "total": None},
            ]
        },
    )


class ResourcesResponse(ResourcesResponseBase, Generic[T]):  # noqa: UP046
    """Complete paginated response SQLModel with resource array.

    This generic model extends ResourcesResponseBase to include the actual
    array of resources for the current page.

    Type Parameters:
        T: The type of resources in the response array

    Attributes:
        resources: Array of resources in current page (max 100 items)

    Inherits from ResourcesResponseBase:
        next: Optional next page cursor
        prev: Optional previous page cursor
        total: Optional total count

    """

    resources: list[T] = Field(
        description="Array of resources in current page", max_length=FieldLimits.MAX_ITEMS_PER_PAGE
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
