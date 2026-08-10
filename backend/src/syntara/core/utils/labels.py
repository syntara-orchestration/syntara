"""Label filtering utilities for key-value label matching.

This module provides functions for matching resources by label key-value pairs
using AND logic (all filter labels must match).
"""

import re
from typing import Any, TypeVar

from sqlalchemy import Select
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, and_, cast
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from syntara.core.exceptions import SafeValueError

# Type variable for generic Query/Select type
TP = TypeVar("TP", bound=tuple[Any, ...])

# Regex pattern to match label filter parameters: labels[key]
LABEL_PARAM_PATTERN = re.compile(r"^labels\[([^]]+)\]$")


def matches(resource_labels: dict[str, str] | None, filter_labels: dict[str, str]) -> bool:
    """Check if resource labels match filter criteria.

    Args:
        resource_labels: Labels on the resource (can be None)
        filter_labels: Label criteria to match against

    Returns:
        True if all filter labels exist in resource labels with matching values

    Examples:
        >>> matches(
        ...     {"env": "prod", "region": "us-east-1", "team": "platform"},
        ...     {"env": "prod", "region": "us-east-1"}
        ... )
        True

        >>> matches(
        ...     {"env": "staging"},
        ...     {"env": "prod"}
        ... )
        False

        >>> matches(None, {})
        True

    """
    # Empty filter matches any resource
    if not filter_labels:
        return True

    # None or empty resource labels can't match non-empty filter
    if not resource_labels:
        return False

    # All filter labels must exist in resource labels with exact values
    return all(resource_labels.get(filter_key) == filter_value for filter_key, filter_value in filter_labels.items())


def parse_label_filter(params: dict[str, str]) -> dict[str, str]:
    """Parse label filter parameters from query parameters.

    Extracts label filters from parameters with the pattern: labels[key]=value

    Args:
        params: Dictionary of query parameters from request

    Returns:
        Dictionary of label key-value pairs to filter by

    Examples:
        >>> params = {
        ...     "labels[environment]": "production",
        ...     "labels[region]": "us-east-1",
        ...     "other_param": "ignored"
        ... }
        >>> parse_label_filter(params)
        {"environment": "production", "region": "us-east-1"}

    """
    label_filters = {}

    for param_name, param_value in params.items():
        # Try to match label parameter pattern
        match = LABEL_PARAM_PATTERN.match(param_name)
        if match:
            label_key = match.group(1)
            label_filters[label_key] = param_value

    return label_filters


def parse_labels_query(labels: str) -> dict[str, str]:
    """Parse labels query parameter from key-value format.

    Supports two formats:
    - "key=value,key2=value2" - filters by key-value pairs
    - "key,key2" - filters by key existence (empty string value)

    Args:
        labels: Labels query string

    Returns:
        Dictionary of label filters

    Examples:
        >>> parse_labels_query("environment=production,team=data")
        {"environment": "production", "team": "data"}
        >>> parse_labels_query("environment,team")
        {"environment": "", "team": ""}

    """
    result: dict[str, str] = {}
    if not labels:
        return result

    for pair_raw in labels.split(","):
        pair = pair_raw.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
        else:
            # Key existence check - use empty string as placeholder
            result[pair] = ""

    return result


def apply_label_filters(
    query: Select[TP] | SelectOfScalar[TP], label_filters: dict[str, str], model: type[SQLModel]
) -> Select[TP] | SelectOfScalar[TP]:
    """Apply label filters to a SQLAlchemy Query using JSON operations.

    Args:
        query: SQLAlchemy Query object or SQLModel Select statement to filter
        label_filters: Label key-value pairs to match
        model: SQLModel class to get labels field attribute from

    Returns:
        Filtered query object of the same type as input

    Examples:
        >>> # With SQLModel Select
        >>> stmt = select(Resource)
        >>> filtered_stmt = apply_label_filters(stmt, {"env": "prod"}, Resource)

        >>> # With SQLAlchemy Query
        >>> query = session.query(Resource)
        >>> filtered_query = apply_label_filters(query, {"region": "us-east-1"}, Resource)

    """
    if not label_filters:
        return query

    # Get the labels field attribute from the model
    if not hasattr(model, "labels"):
        msg = "Label filtering is not supported for this resource"
        raise SafeValueError(msg)

    labels_field = model.labels
    conditions = []

    for key, value in label_filters.items():
        # Use PostgreSQL JSONB operator for label matching
        # This creates conditions like: Resource.labels::jsonb @> :param_1
        # The @> operator checks if the left JSONB contains the right JSONB
        # Build JSONB dict that will be bound as a parameter (prevents SQL injection)
        json_dict = {key: value}
        labels_field_jsonb = cast(labels_field, JSONB)
        # SQLAlchemy will automatically bind this dict as a JSONB parameter
        condition = labels_field_jsonb.contains(json_dict)
        conditions.append(condition)

    # Apply all conditions with AND logic
    if conditions:
        query = query.filter(and_(*conditions))

    return query
