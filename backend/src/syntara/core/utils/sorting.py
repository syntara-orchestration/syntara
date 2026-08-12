"""Sort parameter parsing utilities.

This module provides functions for converting ±field syntax into
structured sort field and direction information.

Syntax:
    - field: Ascending sort on field
    - -field: Descending sort on field

Examples:
    "name" -> ("name", SortDirection.ASC)
    "-created_at" -> ("created_at", SortDirection.DESC)

"""

from typing import Any, TypeVar

from sqlalchemy import Select
from sqlmodel import SQLModel, asc, desc
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from syntara.core.exceptions import SafeValueError
from syntara.core.utils.cursor import SortDirection

# Type variable for generic Query/Select type
TP = TypeVar("TP", bound=tuple[Any, ...])


def parse_sort(
    sort_param: str | None,
    allowed_fields: list[str],
    default_field: str = "created_at",
    default_direction: SortDirection = SortDirection.DESC,
) -> tuple[str, SortDirection]:
    """Parse sort parameter into (field, direction) tuple.

    Args:
        sort_param: Sort parameter from query string (e.g., "name" or "-created_at")
        allowed_fields: List of field names that can be sorted
        default_field: Default field to sort by if sort_param is None/empty
        default_direction: Default direction if sort_param is None/empty

    Returns:
        Tuple of (field_name, sort_direction)

    Raises:
        ValueError: If field name is not in allowed_fields

    Examples:
        >>> parse_sort("name", ["name", "created_at"])
        ("name", SortDirection.ASC)

        >>> parse_sort("-created_at", ["name", "created_at"])
        ("created_at", SortDirection.DESC)

        >>> parse_sort(None, ["created_at"])
        ("created_at", SortDirection.DESC)

    """
    # Use defaults if no sort parameter provided
    if not sort_param:
        if default_field not in allowed_fields:
            msg = f"Default field '{default_field}' not in allowed_fields"
            raise SafeValueError(msg)
        return default_field, default_direction

    # Check for descending prefix
    if sort_param.startswith("-"):
        field_name = sort_param[1:]  # Remove the minus prefix
        direction = SortDirection.DESC
    else:
        field_name = sort_param
        direction = SortDirection.ASC

    # Validate field name
    if field_name not in allowed_fields:
        msg = f"Invalid field: {field_name}"
        raise SafeValueError(msg)

    return field_name, direction


def apply_sorting(
    query: Select[TP] | SelectOfScalar[TP], sort_tuples: list[tuple[str, SortDirection]], model: type[SQLModel]
) -> Select[TP] | SelectOfScalar[TP]:
    """Apply sorting to a SQLAlchemy Query using SQLAlchemy object model.

    Args:
        query: SQLAlchemy Query object or SQLModel Select statement to sort
        sort_tuples: List of (field_name, sort_direction) tuples
        model: SQLModel class to get field attributes from

    Returns:
        Sorted query object of the same type as input

    Examples:
        >>> # With SQLModel Select
        >>> stmt = select(Resource)
        >>> sorted_stmt = apply_sorting(stmt, [("name", SortDirection.ASC)], Resource)

        >>> # With multiple sorts
        >>> sorts = [("name", SortDirection.ASC), ("created_at", SortDirection.DESC)]
        >>> sorted_stmt = apply_sorting(stmt, sorts, Resource)

    """
    if not sort_tuples:
        return query

    order_by_clauses = []
    for field_name, direction in sort_tuples:
        # Get the field attribute from the model
        if not hasattr(model, field_name):
            msg = f"Invalid sort field: {field_name}"
            raise SafeValueError(msg)

        field_attr = getattr(model, field_name)

        # Apply sorting direction using SQLAlchemy functions
        if direction == SortDirection.ASC:
            order_by_clauses.append(asc(field_attr))
        else:  # SortDirection.DESC
            order_by_clauses.append(desc(field_attr))

    # Apply all sorting clauses to the query
    return query.order_by(*order_by_clauses)


def sort_merged_resources[T](resources: list[T], sort: str | None) -> list[T]:
    """Re-sort a merged list of in-memory + DB resources by the sort parameter.

    None values sort to end regardless of direction.
    """
    if not sort or not resources:
        return resources

    descending = sort.startswith("-")
    field = sort.lstrip("-")

    def key_fn(r: T) -> tuple[int, Any]:
        val = getattr(r, field, None)
        if val is None:
            return (0,) if descending else (1,)  # type: ignore[return-value]
        return (1, val) if descending else (0, val)

    resources.sort(key=key_fn, reverse=descending)
    return resources
