"""Filter parsing utilities for bracket notation query parameters.

This module provides functions for converting URL query parameters with
bracket notation into structured filter objects for database queries.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel
from sqlalchemy import Select
from sqlmodel import SQLModel, and_, or_

# We need to import this protected type to pass mypy type-checking
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from syntara.core.exceptions import SafeValueError

# Logger for this module
logger = structlog.stdlib.get_logger(__name__)

# Type variable for generic Query/Select type
TP = TypeVar("TP", bound=tuple[Any, ...])

# Type for filter values - more specific than Any
FilterValue = str | int | float | bool | datetime | Enum


class FilterOperator(str, Enum):
    """Supported filter operators for query parameters.

    String values match the expected bracket notation syntax:
    - eq: Exact equality match
    - contains: Substring match (case-insensitive)
    - starts_with: Prefix match (case-insensitive)
    - gt: Greater than comparison
    - gte: Greater than or equal comparison
    - lt: Less than comparison
    - lte: Less than or equal comparison
    - isnull: Null check (true = IS NULL, false = IS NOT NULL)
    """

    EQ = "eq"
    IN = "in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    ISNULL = "isnull"


class Filter(BaseModel):
    """Structured filter object parsed from query parameters.

    Attributes:
        field: Name of the field to filter on
        operator: Filter operator to apply
        value: Value to filter by (supports str, int, float, bool, datetime)

    """

    field: str
    operator: FilterOperator
    value: FilterValue


# Regex pattern to match bracket notation: field[operator]
# Allow dots in field names for nested fields like "configuration.provider_type"
# Allow any characters inside brackets - validation of operator happens later
BRACKET_PATTERN = re.compile(r"^([\w.]+)\[([^]]*)\]$")

# Import label pattern to skip label parameters in filter parsing
# This avoids conflicts between filter parsing and label parsing
LABEL_PARAM_PATTERN = re.compile(r"^labels\[([^]]+)\]$")


def matches_query_param(value: str, field: str, query_params: dict[str, str]) -> bool:
    """Check if *value* matches a query param for *field*, supporting bracket operators.

    Handles both ``field=exact`` and ``field[contains]=substring`` forms.
    Returns True when no matching param exists (no constraint).
    """
    if field in query_params:
        return value == query_params[field]
    for param_key, param_val in query_params.items():
        m = BRACKET_PATTERN.match(param_key)
        if not m or m.group(1) != field:
            continue
        op = m.group(2)
        if op == "in":
            return value in [v.strip() for v in param_val.split(",")]
        if op == "contains":
            return param_val.lower() in value.lower()
        if op == "startswith":
            return value.lower().startswith(param_val.lower())
        return value == param_val
    return True


def _split_values(raw: str, field: str, operator: FilterOperator) -> list[Filter]:
    """Split a comma-separated parameter value into Filter objects.

    For the IN operator, blank segments are skipped (e.g. ``status[in]=a,,b``
    produces two filters). For all other operators, empty strings are preserved
    so that ``?field=`` still filters for the empty value.
    """
    if operator == FilterOperator.IN:
        return [Filter(field=field, operator=operator, value=v) for val in raw.split(",") if (v := val.strip())]
    return [Filter(field=field, operator=operator, value=val.strip()) for val in raw.split(",")]


def parse_filters(params: dict[str, str], allowed_fields: list[str]) -> list[Filter]:
    """Parse query parameters into structured filter objects.

    Supports both shorthand equality syntax (field=value) and explicit
    bracket notation (field[operator]=value) for advanced filtering.

    Args:
        params: Dictionary of query parameters from request
        allowed_fields: List of field names that can be filtered

    Returns:
        List of Filter objects parsed from parameters

    Raises:
        ValueError: If invalid field name or operator is used

    Examples:
        >>> params = {"name[contains]": "test", "status": "active"}
        >>> parse_filters(params, ["name", "status"])
        [Filter(field="name", operator=CONTAINS, value="test"),
         Filter(field="status", operator=EQ, value="active")]

    """
    filters: list[Filter] = []

    for param_name, param_value in params.items():
        # Skip label parameters - they should be handled by label filtering logic
        if LABEL_PARAM_PATTERN.match(param_name):
            continue

        # Try to match bracket notation first
        bracket_match = BRACKET_PATTERN.match(param_name)

        # Query string params is guaranteed to be dict[str, str] however some unit tests use other types.
        param_str: str = str(param_value)

        if bracket_match:
            # Bracket notation: field[operator]=value
            field_name, operator_str = bracket_match.groups()

            # Validate field name
            if field_name not in allowed_fields:
                msg = f"Invalid field: {field_name}"
                raise SafeValueError(msg)

            # Validate operator
            if operator_str not in FilterOperator.__members__.values():
                msg = f"Invalid operator: {operator_str}"
                raise SafeValueError(msg)

            operator = FilterOperator(operator_str)

            filters.extend(_split_values(param_str, field_name, operator))

        else:
            # Shorthand notation: field=value (implies equality)
            field_name = param_name

            # Validate field name
            if field_name not in allowed_fields:
                msg = f"Invalid field: {field_name}"
                raise SafeValueError(msg)

            filters.extend(_split_values(param_str, field_name, FilterOperator.EQ))

    return filters


def _sanitize_like_value(value: FilterValue) -> str:
    """Sanitize value for use in LIKE/ILIKE patterns to prevent injection.

    Args:
        value: Value to sanitize for LIKE pattern

    Returns:
        Sanitized string value with special characters escaped

    Security Note:
        Escapes % and _ characters that have special meaning in SQL LIKE patterns
        to prevent injection attacks through pattern manipulation.

    """
    if not isinstance(value, str):
        value = str(value)

    # Escape special LIKE pattern characters
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _convert_datetime_value(value: str, field_attr: Any) -> datetime:  # noqa: ANN401
    """Convert string value to datetime.

    Args:
        value: String value to convert
        field_attr: SQLAlchemy field attribute for error context

    Returns:
        Parsed datetime object

    Raises:
        ValueError: If datetime conversion fails

    """
    try:
        # Try parsing as ISO 8601 format (with 'Z' suffix or timezone)
        # Replace 'Z' with '+00:00' for fromisoformat compatibility
        iso_value = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(iso_value)
    except ValueError as e:
        # Log warning and re-raise - malformed timestamps should fail loudly
        logger.warning(
            "Failed to parse datetime value",
            value=value,
            field=getattr(field_attr, "key", "unknown"),
            error=str(e),
        )
        msg = f"Invalid datetime format: {value}. Expected ISO 8601 format (e.g., '2025-01-15T10:30:00Z')"
        raise SafeValueError(msg) from e


def _convert_boolean_value(value: str) -> bool:
    """Convert string value to boolean.

    Args:
        value: String value to convert

    Returns:
        Boolean value

    Raises:
        ValueError: If boolean conversion fails

    """
    try:
        # Convert common string representations to boolean
        lower_value = value.lower().strip()
        if lower_value in ("true", "1", "yes", "on"):
            return True
        if lower_value in ("false", "0", "no", "off"):
            return False
        msg = f"Invalid boolean value: {value}. Expected 'true', 'false', '1', '0', 'yes', 'no', 'on', or 'off'"
        raise SafeValueError(msg)
    except AttributeError as e:
        # If value doesn't have lower() method, it's not a string
        msg = f"Invalid boolean value: {value}. Expected string representation of boolean"
        raise SafeValueError(msg) from e


def _convert_numeric_value(value: str, python_type: type[int | float], field_attr: Any) -> int | float:  # noqa: ANN401
    """Convert string value to numeric type.

    Args:
        value: String value to convert
        python_type: Target numeric type (int or float)
        field_attr: SQLAlchemy field attribute for error context

    Returns:
        Converted numeric value

    Raises:
        ValueError: If numeric conversion fails

    """
    try:
        converted_value = python_type(value)
        # Ensure we return the expected type
        if python_type is int:
            return int(converted_value)
        if python_type is float:
            return float(converted_value)
        # This shouldn't happen given the function's usage, but for type safety
        return float(converted_value)
    except ValueError as e:
        # Log warning and re-raise - type mismatches should fail loudly
        logger.warning(
            "Failed to convert value to numeric type",
            value=value,
            python_type=python_type.__name__,
            field=getattr(field_attr, "key", "unknown"),
            error=str(e),
        )
        msg = f"Invalid {python_type.__name__} value: {value}"
        raise SafeValueError(msg) from e


def _convert_enum_value(value: str, python_type: type[Enum], field_attr: Any) -> Enum:  # noqa: ANN401
    """Convert string value to enum type.

    Args:
        value: String value to convert
        python_type: Target enum type
        field_attr: SQLAlchemy field attribute for error context

    Returns:
        Enum instance

    Raises:
        ValueError: If enum value is invalid

    """
    try:
        # Try to create the enum instance from the string value
        return python_type(value)
    except ValueError as e:
        # Get valid values for error message
        valid_values = [item.value for item in python_type.__members__.values()]
        field_name = getattr(field_attr, "key", "unknown")
        logger.warning(
            "Invalid enum value",
            value=value,
            field=field_name,
            valid_values=valid_values,
        )
        msg = f"Invalid value '{value}' for field '{field_name}'. Valid values are: {', '.join(valid_values)}"
        raise SafeValueError(msg) from e


def _convert_filter_value(value: FilterValue, field_attr: Any) -> FilterValue:  # noqa: ANN401, PLR0911
    """Convert filter value to the appropriate type based on the field.

    Args:
        value: Raw filter value (usually a string from query params)
        field_attr: SQLAlchemy field attribute to infer type from

    Returns:
        Converted value of the appropriate type

    Raises:
        ValueError: If datetime conversion fails with invalid format or if enum value is invalid

    """
    # If value is already the right type, return as-is
    if not isinstance(value, str):
        return value

    # Try to infer type from the field's Python type
    try:
        # Get the Python type from the SQLAlchemy column
        python_type = field_attr.type.python_type
    except (AttributeError, NotImplementedError):
        # Some SQLAlchemy types don't implement python_type (like UUID, custom types)
        # This is expected, just use string comparison for these fields
        logger.debug(
            "Field does not provide python_type, using string comparison",
            field=getattr(field_attr, "key", "unknown"),
        )
        return value

    # Handle enum fields with validation
    if isinstance(python_type, type) and issubclass(python_type, Enum):
        return _convert_enum_value(value, python_type, field_attr)

    # Handle datetime fields
    if python_type == datetime or (hasattr(python_type, "__origin__") and python_type.__origin__ == datetime):
        return _convert_datetime_value(value, field_attr)

    # Handle boolean fields
    if python_type is bool:
        return _convert_boolean_value(value)

    # Handle numeric types
    if python_type in (int, float):
        return _convert_numeric_value(value, python_type, field_attr)

    # For other types (str, UUID, custom types), use string comparison
    return value


def _build_condition(field_attr: Any, operator: FilterOperator, value: FilterValue) -> Any:  # noqa: ANN401, PLR0911
    """Build a SQLAlchemy condition for a single filter.

    Args:
        field_attr: SQLAlchemy field attribute from the model
        operator: Filter operator to apply
        value: Value to filter by

    Returns:
        SQLAlchemy condition object

    """
    # Convert value to appropriate type based on field
    converted_value = _convert_filter_value(value, field_attr)

    match operator:
        case FilterOperator.EQ | FilterOperator.IN:
            return field_attr == converted_value
        case FilterOperator.CONTAINS:
            sanitized_value = _sanitize_like_value(converted_value)
            return field_attr.ilike(f"%{sanitized_value}%")
        case FilterOperator.STARTS_WITH:
            sanitized_value = _sanitize_like_value(converted_value)
            return field_attr.ilike(f"{sanitized_value}%")
        case FilterOperator.GT:
            return field_attr > converted_value
        case FilterOperator.GTE:
            return field_attr >= converted_value
        case FilterOperator.LT:
            return field_attr < converted_value
        case FilterOperator.LTE:
            return field_attr <= converted_value
        case FilterOperator.ISNULL:
            if _convert_boolean_value(str(converted_value)):
                return field_attr.is_(None)
            return field_attr.isnot(None)


def apply_filters(
    query: Select[TP] | SelectOfScalar[TP], filters: list[Filter], model: type[SQLModel]
) -> Select[TP] | SelectOfScalar[TP]:
    """Apply filters to a SQLAlchemy Query or SQLModel Select using Query API.

    Groups filters by ``(field, operator)`` and applies OR logic within each
    group (so comma-separated values of the same operator are unioned), then
    AND logic between different groups.  This means:

    - Same field, same operator, multiple values → OR (the ``?name=alice,bob``
      case).
    - Same field, *different* operators → AND (the range-filter case:
      ``?created_at[gte]=X&created_at[lte]=Y`` becomes
      ``created_at >= X AND created_at <= Y``).
    - Different fields → AND.

    Args:
        query: SQLAlchemy Query object or SQLModel Select statement to filter
        filters: List of Filter objects to apply
        model: SQLModel class to get field attributes from

    Returns:
        Filtered query object of the same type as input

    Examples:
        >>> # Single field with OR (same operator): ?name=alice,bob
        >>> # Becomes: WHERE name = 'alice' OR name = 'bob'

        >>> # Same field, different operators (range): ?created_at[gte]=X&created_at[lte]=Y
        >>> # Becomes: WHERE created_at >= X AND created_at <= Y

        >>> # Different fields with AND: ?name=alice,bob&status=active
        >>> # Becomes: WHERE (name = 'alice' OR name = 'bob') AND status = 'active'

    """
    if not filters:
        return query

    # Group filters by (field, operator) so multiple values of the same
    # operator (e.g. ?name=alice,bob) are OR'd, while different operators on
    # the same field (e.g. [gte] + [lte]) are AND'd via the outer combine.
    operator_groups: dict[tuple[str, FilterOperator], list[Filter]] = {}

    for filter_obj in filters:
        # Validate field exists on model
        if not hasattr(model, filter_obj.field):
            msg = f"Invalid filter field: {filter_obj.field}"
            raise SafeValueError(msg)

        operator_groups.setdefault((filter_obj.field, filter_obj.operator), []).append(filter_obj)

    # Build conditions: OR within each (field, operator) group, AND between groups.
    group_conditions = []

    for (field_name, operator), group_filters in operator_groups.items():
        field_attr = getattr(model, field_name)

        filter_conditions = [_build_condition(field_attr, operator, f.value) for f in group_filters]

        if len(filter_conditions) == 1:
            group_conditions.append(filter_conditions[0])
        else:
            group_conditions.append(or_(*filter_conditions))

    if group_conditions:
        query = query.filter(and_(*group_conditions))

    return query
