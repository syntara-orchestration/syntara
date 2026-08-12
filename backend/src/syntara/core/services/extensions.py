"""Service extension protocols for customizing BaseService behavior.

This module defines protocols that allow services to customize query enrichment,
resource conversion, and post-processing behaviors in BaseService.
"""

from typing import Any, Protocol, runtime_checkable

from sqlalchemy import Select
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from syntara.core.services.types import TModel


@runtime_checkable
class EnrichQueryMixin(Protocol):
    """Protocol for enriching database queries with custom options."""

    def enrich(
        self, query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]]
    ) -> Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]]:
        """Extend the query with custom options before execution.

        Implementations should add query options like selectinload, joinedload,
        or other SQLAlchemy query enhancements as needed.

        Args:
            query: The SQLAlchemy query to enrich

        Returns:
            Enriched query with additional options applied

        """


@runtime_checkable
class ConvertResourceMixin(Protocol):
    """Protocol for converting database resources to response format."""

    def convert_resource(self, resource: TModel) -> Any:  # noqa: ANN401
        """Convert database resource to response format.

        Implementations should transform database models into appropriate
        response objects, such as Pydantic models with additional fields
        or computed properties.

        Args:
            resource: Database resource to convert

        Returns:
            Converted resource in the desired response format

        """


@runtime_checkable
class PostProcessingMixin(Protocol):
    """Protocol for post-processing database resources before response conversion."""

    async def post_process(self, resources: list[TModel]) -> None:
        """Process resources after database query but before response conversion.

        Implementations can perform operations like syncing status from external
        services, enriching data, or applying business logic that requires
        the full result set.

        Args:
            resources: List of database resources to process

        """
