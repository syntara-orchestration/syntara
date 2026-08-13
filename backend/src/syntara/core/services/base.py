"""Base service class for standardized data operations.

This module provides a single base class that ALL services must inherit from to ensure
consistent filtering, sorting, pagination, and label handling across the entire system.
"""

import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Integer, Select, cast, func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql._expression_select_cls import SelectOfScalar

# Import individual utilities to avoid circular imports
from syntara.authz.engine import AllowedProjectsResult
from syntara.core.constants import FieldLimits
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.services.extensions import ConvertResourceMixin, EnrichQueryMixin, PostProcessingMixin
from syntara.core.services.types import TModel, TResponse
from syntara.core.utils.cursor import (
    PaginationDirection,
    SortDirection,
    decode_cursor,
    deserialize_column_sort_value,
    extract_keyset_from_cursor,
)
from syntara.core.utils.filters import Filter, apply_filters, parse_filters
from syntara.core.utils.labels import apply_label_filters, parse_label_filter, parse_labels_query
from syntara.core.utils.pagination import PaginationResult, generate_response
from syntara.core.utils.sorting import apply_sorting, parse_sort

logger = structlog.stdlib.get_logger(__name__)


class DefaultEnrichQueryMixin(EnrichQueryMixin):
    """Default implementation of EnrichQueryMixin that performs no query enrichment."""

    def enrich(
        self, query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]]
    ) -> Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]]:
        """Extend the query with custom options before execution.

        This is a no-op implementation that returns the query unchanged.
        Subclasses can override this method to add query options like selectinload.

        Args:
            query: The SQLAlchemy query to extend

        Returns:
            Extended query (by default, returns the query unchanged)

        """
        return query


class DefaultConvertResourceMixin(ConvertResourceMixin):
    """Default implementation of ConvertResourceMixin that performs no conversion."""

    def convert_resource(self, resource: TModel) -> Any:  # noqa: ANN401
        """Convert database resource to response format.

        This is a no-op implementation that returns the resource as-is.
        Subclasses can override this method to provide custom conversion logic.

        Args:
            resource: Database resource to convert

        Returns:
            Converted resource (by default, returns the resource unchanged)

        """
        return resource


class DefaultPostProcessingMixin(PostProcessingMixin):
    """Default implementation of PostProcessingMixin that performs no post-processing."""

    async def post_process(self, resources: list[TModel]) -> None:
        """Process resources after database query but before response conversion.

        This is a no-op implementation that does nothing.
        Subclasses can override this method to provide custom processing logic.

        Args:
            resources: List of database resources to process

        """


class BaseService:
    """Base service class for ALL data operations.

    This class provides the ONLY way to handle filtering, sorting, pagination,
    and label filtering across all services. All services MUST inherit from this
    class and use these methods to ensure consistency.
    """

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        enrich_query_mixin: EnrichQueryMixin | None = None,
        convert_resource_mixin: ConvertResourceMixin | None = None,
        post_processing_mixin: PostProcessingMixin | None = None,
    ) -> None:
        """Initialize service with database session and current user.

        Args:
            session: Async database session for operations
            user: Current authenticated user for audit tracking
            enrich_query_mixin: Mixin to support extending database queries before execution
            convert_resource_mixin: Mixin to support converting database objects to response objects
            post_processing_mixin: Mixin to support post-processing of database objects

        """
        self.session = session
        self.user = user
        self.enrich_query_mixin = enrich_query_mixin if enrich_query_mixin is not None else DefaultEnrichQueryMixin()
        self.convert_resource_mixin = (
            convert_resource_mixin if convert_resource_mixin is not None else DefaultConvertResourceMixin()
        )
        self.post_processing_mixin = (
            post_processing_mixin if post_processing_mixin is not None else DefaultPostProcessingMixin()
        )

    @staticmethod
    def _collect_user_ids(objects: Sequence[Any], field_names: Sequence[str]) -> set[str | UUID]:
        ids: set[str | UUID] = set()
        for obj in objects:
            for field in field_names:
                val = getattr(obj, field, None)
                if val:
                    ids.add(val)
        return ids

    @staticmethod
    def _apply_user_map(objects: Sequence[Any], field_names: Sequence[str], user_map: dict[str | UUID, str]) -> None:
        for obj in objects:
            for field in field_names:
                val = getattr(obj, field, None)
                if val and val in user_map:
                    setattr(obj, field, user_map[val])

    async def _resolve_user_fields(
        self,
        objects: Sequence[Any],
        field_names: Sequence[str] = ("created_by", "updated_by"),
    ) -> None:
        """Resolve user UUID fields to usernames in-place.

        Cosmetic enrichment — if the query fails, UUIDs are left in place.
        """
        user_ids = self._collect_user_ids(objects, field_names)
        if not user_ids:
            return
        try:
            stmt = select(User.id, User.username).where(User.id.in_(user_ids))  # type: ignore[attr-defined]
            result = await self.session.exec(stmt)
            user_map: dict[str | UUID, str] = {row[0]: row[1] for row in result}
        except (SQLAlchemyError, OSError):
            logger.warning("Failed to resolve usernames; returning UUIDs", exc_info=True)
            return
        unresolved = user_ids - set(user_map.keys())
        if unresolved:
            logger.debug(
                "Some user UUIDs could not be resolved to usernames", unresolved_ids=[str(uid) for uid in unresolved]
            )
        self._apply_user_map(objects, field_names, user_map)

    def _apply_standard_filters(
        self,
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
        query_params: dict[str, str],
        model: type[TModel],
        special_field_handlers: dict[str, Any] | None = None,
    ) -> tuple[Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]], list[Filter]]:
        """Apply standard filters to query.

        Args:
            query: SQLAlchemy query to filter
            query_params: Query parameters for filtering
            model: BaseResource class to apply filters to (reads __filterable_fields__)
            special_field_handlers: Dict mapping field names to custom handler functions

        Returns:
            Tuple of (filtered_query, filter_objects)

        """
        filters = parse_filters(query_params, model.__filterable_fields__)

        # Separate regular filters from special filters
        special_fields = set(special_field_handlers.keys()) if special_field_handlers else set()
        regular_filters = [f for f in filters if f.field not in special_fields]

        # Apply only regular filters here; special filters are handled separately
        filtered_query = apply_filters(query, regular_filters, model) if regular_filters else query

        return filtered_query, filters

    def _apply_label_filters(
        self,
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
        query_params: dict[str, str],
        model: type[TModel],
    ) -> tuple[Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]], dict[str, str]]:
        """Apply label filters to query using both bracket notation and labels param.

        Args:
            query: SQLAlchemy query to filter
            query_params: Query parameters for filtering
            model: BaseResource class to apply filters to

        Returns:
            Tuple of (filtered_query, label_filters_dict)

        """
        # Parse label filters from bracket notation (labels[key]=value)
        label_filters = parse_label_filter(query_params)

        # Apply label filters if any were found
        if label_filters:
            # Handle empty values (key existence checks) differently than PostgreSQL JSONB
            existence_filters = {k: v for k, v in label_filters.items() if v == ""}
            value_filters = {k: v for k, v in label_filters.items() if v != ""}

            # Apply exact value filters using JSONB contains
            if value_filters:
                query = apply_label_filters(query, value_filters, model)

            # Apply existence filters using has_key
            if existence_filters and hasattr(model, "labels"):
                for key in existence_filters:
                    query = query.filter(model.labels.has_key(key))  # type: ignore[attr-defined]

        return query, label_filters

    def _apply_special_filters(
        self,
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
        filters: list[Filter],
        model: type[TModel],
        special_field_handlers: dict[str, Any] | None = None,
    ) -> Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]]:
        """Apply special filters that require custom handling (e.g., JSON fields).

        Args:
            query: SQLAlchemy query to filter
            filters: List of filter objects to apply
            model: BaseResource class to get field attributes from
            special_field_handlers: Dict mapping field names to custom handler functions

        Returns:
            Query with special filters applied

        """
        if not special_field_handlers:
            return query

        for filter_obj in filters:
            if filter_obj.field in special_field_handlers:
                handler = special_field_handlers[filter_obj.field]
                query = handler(query, filter_obj, model)

        return query

    def _apply_sorting(
        self,
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
        sort: str | None,
        model: type[TModel],
        *,
        reverse_for_backward: bool = False,
    ) -> tuple[Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]], str, SortDirection]:
        """Apply sorting to query with automatic ID tiebreaker.

        This method ensures stable, deterministic ordering by:
        1. Applying the requested sort field (e.g., created_at DESC)
        2. Adding ID as a tiebreaker to prevent non-deterministic ordering when
           multiple items have identical values for the sort field

        The ID tiebreaker is CRITICAL for cursor-based pagination to prevent:
        - Duplicate items appearing across pages
        - Items being skipped during pagination
        - Inconsistent ordering between forward and backward navigation

        For backward pagination, the sort direction is reversed to fetch items
        in the opposite order, which are then reversed in memory to maintain
        display consistency.

        Args:
            query: SQLAlchemy query to sort
            sort: Sort parameter (e.g., "-created_at" for DESC, "name" for ASC)
            model: BaseResource class to apply sorting to (reads __sortable_fields__)
            reverse_for_backward: If True, reverse the sort direction for backward pagination

        Returns:
            Tuple of (sorted_query, resolved_sort_field, original_sort_direction)

        Example:
            For sort="-created_at":
            - Forward: ORDER BY created_at DESC, id DESC
            - Backward: ORDER BY created_at ASC, id ASC (reversed for fetching)
                       Results are then reversed in memory to display as DESC

        """
        sort_field, sort_direction = parse_sort(sort, model.__sortable_fields__)

        # Reverse sort direction if doing backward pagination
        actual_sort_direction = sort_direction
        if reverse_for_backward:
            actual_sort_direction = SortDirection.ASC if sort_direction == SortDirection.DESC else SortDirection.DESC

        # Always add id as a tiebreaker to ensure stable ordering
        # This is critical for cursor-based pagination when multiple items have the same sort field value
        sort_tuples = [(sort_field, actual_sort_direction), ("id", actual_sort_direction)]
        sorted_query = apply_sorting(query, sort_tuples, model)
        return sorted_query, sort_field, sort_direction

    def _apply_cursor_pagination(
        self,
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
        cursor: str | None,
        sort_field: str,
        sort_direction: SortDirection,
        model: type[TModel],
    ) -> tuple[Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]], bool]:
        """Apply cursor-based pagination using keyset pagination technique.

        Uses a compound keyset ``(sort_field, id)`` that matches the ORDER BY
        produced by ``_apply_sorting``.  When the cursor carries a
        ``sort_value`` (new-style), the WHERE clause filters on the actual sort
        column.  Old cursors without ``sort_value`` fall back to
        ``(created_at, id)`` for backward compatibility.

        Args:
            query: SQLAlchemy query to paginate
            cursor: Cursor token for pagination (None for first page)
            sort_field: Resolved sort field name from ``_apply_sorting``
            sort_direction: Sort direction from sorting step
            model: BaseResource class to get field attributes from

        Returns:
            Tuple of (query with cursor-based pagination applied, needs_reverse flag)

        """
        if not cursor:
            return query, False

        needs_reverse = False

        cursor_data = decode_cursor(cursor)
        cursor_sort_field, cursor_sort_value, resource_id, created_at, direction = extract_keyset_from_cursor(
            cursor_data
        )

        # Decide which column to use for the keyset boundary.
        # New cursors carry sort_value for the actual sort column.
        # Old cursors (or created_at sort) use created_at as before.
        use_sort_col = (
            cursor_sort_value is not None
            and cursor_sort_field is not None
            and cursor_sort_field != "created_at"
            and cursor_sort_field == sort_field
        )

        if resource_id:
            try:
                cursor_id = UUID(resource_id)
            except ValueError:
                # Legacy / partially corrupt keyset id: ignore filter and continue.
                return query, needs_reverse

            if use_sort_col and hasattr(model, sort_field):
                sort_col = getattr(model, sort_field)
                # Cursor tokens store sort_value via serialize_sort_value.
                # Coerce back before keyset compare — otherwise Postgres
                # rejects string vs timestamptz (HTTP 500 on page 2+).
                # SafeValueError from deserialize_column_sort_value propagates as 422.
                cursor_sv = deserialize_column_sort_value(str(cursor_sort_value), sort_col)
                query, needs_reverse = self._apply_keyset_filter(
                    query,
                    sort_col,
                    cursor_sv,
                    model.id,
                    cursor_id,
                    sort_direction,
                    direction,
                )
            elif created_at:
                try:
                    cursor_timestamp = datetime.fromisoformat(created_at)
                except ValueError:
                    # Legacy / partially corrupt created_at: ignore filter and continue.
                    return query, needs_reverse
                query, needs_reverse = self._apply_keyset_filter(
                    query,
                    model.created_at,
                    cursor_timestamp,
                    model.id,
                    cursor_id,
                    sort_direction,
                    direction,
                )

        return query, needs_reverse

    @staticmethod
    def _coerce_boolean_keyset(col: Any, val: Any) -> tuple[Any, Any]:  # noqa: ANN401
        """Cast boolean keyset operands so SQLAlchemy accepts < / > comparisons.

        SQLAlchemy rejects inequalities against boolean True/False literals
        (ArgumentError). Postgres orders false < true, same as 0 < 1.
        """
        if isinstance(val, bool):
            return cast(col, Integer), int(val)
        return col, val

    @staticmethod
    def _apply_keyset_filter(
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
        col_a: Any,  # noqa: ANN401
        val_a: Any,  # noqa: ANN401
        col_b: Any,  # noqa: ANN401
        val_b: Any,  # noqa: ANN401
        sort_direction: SortDirection,
        pagination_direction: PaginationDirection,
    ) -> tuple[Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]], bool]:
        """Apply a two-column keyset WHERE clause matching ORDER BY ``(col_a, col_b)``.

        Returns (filtered_query, needs_reverse).
        """
        needs_reverse = False
        is_desc = sort_direction.value == "desc"

        col_a, val_a = BaseService._coerce_boolean_keyset(col_a, val_a)

        if pagination_direction == PaginationDirection.NEXT:
            if is_desc:
                query = query.filter((col_a < val_a) | ((col_a == val_a) & (col_b < val_b)))
            else:
                query = query.filter((col_a > val_a) | ((col_a == val_a) & (col_b > val_b)))
        elif is_desc:
            query = query.filter((col_a > val_a) | ((col_a == val_a) & (col_b > val_b)))
            needs_reverse = True
        else:
            query = query.filter((col_a < val_a) | ((col_a == val_a) & (col_b < val_b)))
            needs_reverse = True

        return query, needs_reverse

    async def _check_has_items_before(
        self,
        first_item: TModel,
        query_params: dict[str, str],
        filters: list[Filter],
        sort: str | None,
        model: type[TModel],
        special_field_handlers: dict[str, Any] | None = None,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> bool:
        """Check if any items exist before the given item (toward first page).

        This method is used during backward pagination to determine if we've reached
        the first page. It executes a separate query to check for items that would
        appear BEFORE the first item in the current result set.

        During backward pagination with DESC sort:
        - "Before" means items with created_at > first_item.created_at
        - These are newer items (toward the first page)

        During backward pagination with ASC sort:
        - "Before" means items with created_at < first_item.created_at
        - These are older items (toward the first page)

        Args:
            first_item: The first item in the current result set
            query_params: Query parameters for filtering
            filters: List of filter objects to apply
            sort: Sort parameter (e.g., "-created_at")
            model: BaseResource class to query
            special_field_handlers: Dict mapping field names to custom handler functions
            allowed_projects: Optional project scope filter result

        Returns:
            True if items exist before first_item (not on first page)
            False if no items exist before first_item (on first page)

        """
        # Build query with same filters as main query
        check_query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]] = select(model)
        if hasattr(model, "deleted_at"):
            check_query = check_query.filter(model.deleted_at.is_(None))  # type: ignore[attr-defined]

        # Apply project scope filter
        if (
            allowed_projects is not None
            and not allowed_projects.all_projects
            and hasattr(model, "project_id")
            and allowed_projects.project_ids
        ):
            check_query = check_query.filter(
                model.project_id.in_(allowed_projects.project_ids)  # type: ignore[attr-defined]
            )

        # Apply same filters as main query
        check_query, _ = self._apply_standard_filters(check_query, query_params, model, special_field_handlers)
        check_query, _ = self._apply_label_filters(check_query, query_params, model)
        if special_field_handlers:
            check_query = self._apply_special_filters(check_query, filters, model, special_field_handlers)

        # Check if any items exist before first_item using the sort column keyset.
        sort_field_name, original_sort_direction = parse_sort(sort or "-created_at", model.__sortable_fields__)
        sort_col: Any = getattr(model, sort_field_name, model.created_at)
        sort_val: Any = getattr(first_item, sort_field_name, first_item.created_at)
        sort_col, sort_val = BaseService._coerce_boolean_keyset(sort_col, sort_val)
        if original_sort_direction.value == "desc":
            check_query = check_query.filter(
                (sort_col > sort_val) | ((sort_col == sort_val) & (model.id > first_item.id))
            )
        else:
            check_query = check_query.filter(
                (sort_col < sort_val) | ((sort_col == sort_val) & (model.id < first_item.id))
            )

        check_result = await self.session.exec(check_query.limit(1))  # type: ignore[arg-type]
        return check_result.one_or_none() is not None

    @staticmethod
    def _apply_label_count_filters(
        query: SelectOfScalar[int],
        label_filters: dict[str, str],
        model: type[TModel],
    ) -> SelectOfScalar[int]:
        """Apply label filters to a count query."""
        existence_filters = {k: v for k, v in label_filters.items() if v == ""}
        value_filters = {k: v for k, v in label_filters.items() if v != ""}

        if value_filters:
            query = apply_label_filters(query, value_filters, model)  # type: ignore[assignment]

        if existence_filters and hasattr(model, "labels"):
            for key in existence_filters:
                query = query.filter(model.labels.has_key(key))  # type: ignore[attr-defined]

        return query

    async def _get_total_count(
        self,
        filters: list[Filter],
        model: type[TModel],
        special_field_handlers: dict[str, Any] | None = None,
        label_filters: dict[str, str] | None = None,
        allowed_projects: AllowedProjectsResult | None = None,
        id_restriction: list[UUID] | None = None,
    ) -> int:
        """Get total count of resources matching filters.

        Args:
            filters: List of filter objects to apply
            model: BaseResource class to count
            special_field_handlers: Dict mapping field names to custom handler functions
            label_filters: Dict of label filters to apply
            allowed_projects: Optional project scope filter result
            id_restriction: Optional list of allowed resource IDs

        Returns:
            Total count of matching resources

        """
        count_query = select(func.count()).select_from(model)
        # Only apply soft delete filter if model has deleted_at field
        if hasattr(model, "deleted_at"):
            count_query = count_query.filter(model.deleted_at.is_(None))  # type: ignore[attr-defined]

        # Apply project scope filter
        if allowed_projects is not None and not allowed_projects.all_projects and hasattr(model, "project_id"):
            if not allowed_projects.project_ids:
                return 0
            count_query = count_query.filter(
                model.project_id.in_(allowed_projects.project_ids)  # type: ignore[attr-defined]
            )

        # Apply ID restriction filter
        if id_restriction is not None:
            if not id_restriction:
                return 0
            count_query = count_query.filter(model.id.in_(id_restriction))  # type: ignore[attr-defined]

        # Apply regular filters
        regular_filters = [f for f in filters if not special_field_handlers or f.field not in special_field_handlers]
        if regular_filters:
            count_query = apply_filters(count_query, regular_filters, model)  # type: ignore[assignment]

        # Apply special filters
        if special_field_handlers:
            special_filters = [f for f in filters if f.field in special_field_handlers]
            for filter_obj in special_filters:
                handler = special_field_handlers[filter_obj.field]
                count_query = handler(count_query, filter_obj, model)

        # Apply label filters
        if label_filters:
            count_query = self._apply_label_count_filters(count_query, label_filters, model)

        total_result = await self.session.exec(count_query)
        return total_result.one() or 0

    def _validate_query_params(
        self,
        query_params: dict[str, str],
        model: type[TModel],
    ) -> None:
        """Validate query parameters against model field types using Pydantic.

        Args:
            query_params: Raw query parameters from request
            model: BaseResource class to validate against (reads __filterable_fields__)

        Raises:
            ValueError: If validation fails for any parameter

        """
        for field_name, string_value in query_params.items():
            # Skip validation for fields not in allowed list
            if field_name not in model.__filterable_fields__:
                continue

            # Get field info from model
            field_info = model.model_fields.get(field_name)
            if field_info:
                try:
                    # Just validate, don't store the converted value
                    adapter: TypeAdapter[Any] = TypeAdapter(field_info.annotation)
                    adapter.validate_python(string_value)
                except ValidationError as e:
                    # Extract the first error message for cleaner output
                    error_detail = str(e.errors()[0]["msg"]) if e.errors() else str(e)
                    error_message = f"Invalid value for field '{field_name}': {error_detail}"
                    raise SafeValueError(error_message) from e

    async def list_resources(
        self,
        model: type[TModel],
        response_type: type[TResponse],
        response_type_converter: Callable[[TModel], Any] | None = None,
        post_query_callback: Callable[[list[TModel]], Awaitable[None]] | None = None,
        limit: int = 100,
        cursor: str | None = None,
        sort: str | None = None,
        special_field_handlers: dict[str, Any] | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
        id_restriction: list[UUID] | None = None,
    ) -> TResponse:
        """List resources with unified filtering, sorting, and cursor-based pagination.

        This method provides the unified way to handle filtering, sorting, pagination,
        and label filtering. ALL services MUST use this method for consistency.

        Pagination Strategy:
            Uses industry-standard "Fetch N+1" pattern for cursor-based pagination:
            1. Fetches limit+1 items to detect if more pages exist
            2. Trims to limit items for response
            3. Generates cursors based on boundary items
            4. For backward pagination, requires second query to detect first page

            Benefits:
            - Consistent performance at any page depth (no OFFSET)
            - Handles real-time data changes gracefully
            - Prevents duplicate/missing items with identical timestamps
            - Aligns with Stripe, GitHub, Shopify, GraphQL Relay standards

        Cursor Format:
            Opaque base64-encoded JSON containing:
            - id: UUID of boundary item
            - created_at: Timestamp of boundary item
            - direction: "next" or "prev"

        Filtering:
            Filterable fields are read from model's __filterable_fields__ attribute.
            Supports:
            - Standard field filters (e.g., ?status=active)
            - Label filters (e.g., ?labels[env]=prod)
            - Special field handlers for complex types (JSON, arrays, etc.)

        Sorting:
            Sortable fields are read from model's __sortable_fields__ attribute.
            Always includes ID as tiebreaker for stable ordering.

        Services can override _handle_response_conversion(), _handle_post_processing() and
        _handle_query_enrichment() methods to provide custom response conversion and post-query processing logic.

        Args:
            model: BaseResource class to query (e.g., Workflow)
            response_type: ResourcesResponse subclass to return (e.g., WorkflowListResponse)
            response_type_converter: Optional function to convert database objects to response objects
            post_query_callback: Optional async callback to process database objects before conversion
            limit: Maximum number of resources to return (fetches limit+1 for N+1 pattern)
            cursor: Cursor token for pagination (None for first page)
            sort: Sort parameter (e.g., "name", "-created_at")
            special_field_handlers: Dict mapping field names to custom handler functions
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response (requires extra COUNT query)
            allowed_projects: Optional result from ProjectScopeFilter. When provided, filters
                resources to only those belonging to the user's authorized projects. If
                all_projects is True, no filtering is applied. Requires model to have a
                project_id field.
            id_restriction: Optional list of allowed resource IDs. When provided, filters
                resources to only those whose ID is in the list. If the list is empty,
                returns an empty result immediately. If None, no ID filtering is applied.

        Returns:
            Typed response object containing:
            - resources: List of items (length <= limit)
            - next: Cursor for next page (null if last page)
            - prev: Cursor for previous page (null if first page)
            - total: Total count (only if include_total=True)

        Example:
            response = await service.list_resources(
                model=Workflow,
                response_type=WorkflowListResponse,
                limit=10,
                cursor=None,
                sort="-created_at",
                query_params_items=[("status", "active")],
            )

        """
        limit = min(limit, FieldLimits.MAX_ITEMS_PER_PAGE)

        # Extract filtering parameters from query params, excluding pagination/sorting params
        excluded_params = {"limit", "cursor", "sort", "include_total"}
        query_params: dict[str, str] = {}

        if query_params_items:
            query_params = {key: value for key, value in query_params_items if key not in excluded_params}

        table_name = getattr(model, "__tablename__", model.__name__)
        logger.debug(
            "list_query_start",
            table=table_name,
            limit=limit,
            cursor=cursor,
            sort=sort,
            filter_fields=list(query_params.keys()),
        )

        start = time.monotonic()
        try:
            result = await self._execute_list_query(
                model=model,
                response_type=response_type,
                response_type_converter=response_type_converter,
                post_query_callback=post_query_callback,
                limit=limit,
                cursor=cursor,
                sort=sort,
                special_field_handlers=special_field_handlers,
                query_params=query_params,
                include_total=include_total,
                allowed_projects=allowed_projects,
                id_restriction=id_restriction,
            )
        except Exception:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            logger.exception(
                "list_query_failed",
                table=table_name,
                duration_ms=elapsed_ms,
                filters=query_params,
            )
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.debug(
            "list_query_complete",
            table=table_name,
            duration_ms=duration_ms,
            result_count=len(result.resources),
            has_next=result.next is not None,
            filter_fields=list(query_params.keys()),
        )

        return result

    async def _execute_list_query(
        self,
        model: type[TModel],
        response_type: type[TResponse],
        response_type_converter: Callable[[TModel], Any] | None,
        post_query_callback: Callable[[list[TModel]], Awaitable[None]] | None,
        limit: int,
        cursor: str | None,
        sort: str | None,
        special_field_handlers: dict[str, Any] | None,
        query_params: dict[str, str],
        *,
        include_total: bool,
        allowed_projects: AllowedProjectsResult | None,
        id_restriction: list[UUID] | None = None,
    ) -> TResponse:
        """Execute the list query with filtering, sorting, pagination, and conversion."""
        self._validate_query_params(query_params, model)

        built = self._build_list_query(
            model,
            query_params,
            sort,
            cursor,
            limit,
            special_field_handlers,
            allowed_projects,
            id_restriction=id_restriction,
        )
        if built is None:
            return response_type(resources=[], next=None, prev=None, total=0 if include_total else None)

        query, filters, label_filters, is_backward, sort_field_name, sort_dir = built

        trimmed, pagination = await self._fetch_and_paginate(
            query,
            model,
            query_params,
            (filters, label_filters),
            sort,
            cursor,
            limit,
            include_total=include_total,
            is_backward=is_backward,
            special_field_handlers=special_field_handlers,
            allowed_projects=allowed_projects,
            id_restriction=id_restriction,
            sort_context=(sort_field_name, sort_dir),
        )

        if post_query_callback:
            await post_query_callback(trimmed)
        else:
            await self.post_processing_mixin.post_process(trimmed)

        if response_type_converter:
            converted = [response_type_converter(r) for r in trimmed]
        else:
            converted = [self.convert_resource_mixin.convert_resource(r) for r in trimmed]

        return response_type(
            resources=converted,
            next=pagination["next"],
            prev=pagination["prev"],
            total=pagination["total"],
        )

    @staticmethod
    def _apply_access_filters(
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
        model: type[TModel],
        allowed_projects: AllowedProjectsResult | None,
        id_restriction: list[UUID] | None,
    ) -> Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]] | None:
        """Apply project-scope and ID-restriction filters. Returns None when access yields no results."""
        if allowed_projects is not None and not allowed_projects.all_projects:
            if not hasattr(model, "project_id"):
                msg = f"Model {model.__name__} does not have a project_id field for project scope filtering"
                raise ValueError(msg)
            if not allowed_projects.project_ids:
                return None
            query = query.filter(model.project_id.in_(allowed_projects.project_ids))  # type: ignore[attr-defined]

        if id_restriction is not None:
            if not id_restriction:
                return None
            query = query.filter(model.id.in_(id_restriction))  # type: ignore[attr-defined]

        return query

    def _build_list_query(
        self,
        model: type[TModel],
        query_params: dict[str, str],
        sort: str | None,
        cursor: str | None,
        limit: int,
        special_field_handlers: dict[str, Any] | None,
        allowed_projects: AllowedProjectsResult | None,
        *,
        id_restriction: list[UUID] | None = None,
    ) -> (
        tuple[
            Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
            list[Filter],
            dict[str, str],
            bool,
            str,
            SortDirection,
        ]
        | None
    ):
        """Build filtered, sorted, paginated query. Returns None when access yields no results."""
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]] = select(model)
        if hasattr(model, "deleted_at"):
            query = query.filter(model.deleted_at.is_(None))  # type: ignore[attr-defined]

        result = self._apply_access_filters(query, model, allowed_projects, id_restriction)
        if result is None:
            return None
        query = result

        query, filters = self._apply_standard_filters(query, query_params, model, special_field_handlers)
        query, label_filters = self._apply_label_filters(query, query_params, model)
        if special_field_handlers:
            query = self._apply_special_filters(query, filters, model, special_field_handlers)

        is_backward = False
        if cursor:
            try:
                cursor_data = decode_cursor(cursor)
                is_backward = cursor_data.get("direction", "next") == PaginationDirection.PREV.value
            except (ValueError, KeyError):
                pass

        query, sort_field_name, sort_direction = self._apply_sorting(
            query,
            sort,
            model,
            reverse_for_backward=is_backward,
        )
        query, needs_reverse = self._apply_cursor_pagination(
            query,
            cursor,
            sort_field_name,
            sort_direction,
            model,
        )
        query = query.limit(limit + 1)
        query = self.enrich_query_mixin.enrich(query)

        if needs_reverse:
            is_backward = True

        return query, filters, label_filters, is_backward, sort_field_name, sort_direction

    async def _fetch_and_paginate(
        self,
        query: Select[tuple[TModel]] | SelectOfScalar[tuple[TModel]],
        model: type[TModel],
        query_params: dict[str, str],
        filter_context: tuple[list[Filter], dict[str, str]],
        sort: str | None,
        cursor: str | None,
        limit: int,
        *,
        include_total: bool,
        is_backward: bool,
        special_field_handlers: dict[str, Any] | None,
        allowed_projects: AllowedProjectsResult | None,
        id_restriction: list[UUID] | None = None,
        sort_context: tuple[str, SortDirection] = ("created_at", SortDirection.DESC),
    ) -> tuple[list[TModel], PaginationResult]:
        """Execute query, apply N+1 pagination, and return trimmed resources with metadata."""
        filters, label_filters = filter_context
        sort_field_name, sort_direction = sort_context
        result = await self.session.exec(query)  # type: ignore[arg-type]
        resources = list(result.all())

        if is_backward:
            resources.reverse()

        total_count = None
        if include_total:
            total_count = await self._get_total_count(
                filters,
                model,
                special_field_handlers,
                label_filters,
                allowed_projects,
                id_restriction=id_restriction,
            )

        is_first_page = False
        if is_backward and len(resources) > 0:
            has_items_before = await self._check_has_items_before(  # type: ignore[type-var]
                first_item=resources[0],
                query_params=query_params,
                filters=filters,
                sort=sort,
                model=model,
                special_field_handlers=special_field_handlers,
                allowed_projects=allowed_projects,
            )
            is_first_page = not has_items_before

        pagination = generate_response(
            items=resources,  # type: ignore[arg-type]
            limit=limit,
            cursor=cursor,
            include_total=include_total,
            total_count=total_count,
            is_first_page=is_first_page,
            sort_field=sort_field_name,
            sort_direction=sort_direction,
            sort_value_fn=lambda item: getattr(item, sort_field_name, item.created_at),
        )

        trimmed: list[TModel] = pagination["trimmed_items"]  # type: ignore[assignment]
        return trimmed, pagination

    async def count_resources(
        self,
        model: type[TModel],
        *,
        special_field_handlers: dict[str, Any] | None = None,
        labels_param: str | None = None,
        **query_params: Any,  # noqa: ANN401
    ) -> int:
        """Count resources with unified filtering across all services.

        Args:
            model: BaseResource class to count (reads __filterable_fields__)
            special_field_handlers: Dict mapping field names to custom handler functions
            labels_param: Optional labels query string parameter
            **query_params: Additional query parameters for filtering

        Returns:
            Total count of matching resources

        """
        # Parse filters
        filters = parse_filters(query_params, model.__filterable_fields__)

        # Parse label filters
        label_filters = parse_label_filter(query_params)
        if labels_param:
            additional_labels = parse_labels_query(labels_param)
            label_filters.update(additional_labels)

        return await self._get_total_count(filters, model, special_field_handlers, label_filters)
