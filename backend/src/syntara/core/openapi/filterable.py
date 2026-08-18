"""FilterableModel dependency factory for OpenAPI filter param generation.

Declares filter query parameters on list endpoints by introspecting
``__filterable_fields__`` and model field types.  The ``to_openapi_params()``
method generates deepObject-style OpenAPI parameter dicts that match the
hand-authored sub-spec format.  The export script injects these into the
generated spec so the drift checker can validate consistency.
"""

from __future__ import annotations

import types
from datetime import datetime
from enum import Enum
from typing import Any, get_args, get_origin
from uuid import UUID

from syntara.core.utils.filters import FilterOperator

_OPTIONAL_OPS = {FilterOperator.IN, FilterOperator.ISNULL}
_STRING_OPS = set(FilterOperator) - _OPTIONAL_OPS
_COMPARISON_OPS = _STRING_OPS - {FilterOperator.CONTAINS, FilterOperator.STARTS_WITH}
_EQ_ONLY = {FilterOperator.EQ}

_OPERATOR_TITLES: dict[FilterOperator, str] = {
    FilterOperator.EQ: "Equals",
    FilterOperator.CONTAINS: "Contains",
    FilterOperator.STARTS_WITH: "Starts With",
    FilterOperator.GT: "Greater Than",
    FilterOperator.GTE: "Greater Than or Equal",
    FilterOperator.LT: "Less Than",
    FilterOperator.LTE: "Less Than or Equal",
}


def _unwrap_optional(annotation: Any) -> Any:  # noqa: ANN401
    """Unwrap Optional[X] / X | None to the inner type X."""
    origin = get_origin(annotation)
    if origin is types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


_TYPE_TO_OPERATORS: list[tuple[type, set[FilterOperator]]] = [
    (bool, _EQ_ONLY),
    (datetime, _COMPARISON_OPS),
    (UUID, _EQ_ONLY),
    (Enum, _EQ_ONLY),
    (int, _COMPARISON_OPS),
    (float, _COMPARISON_OPS),
    (str, _STRING_OPS),
]


def _classify_python_type(python_type: type) -> set[FilterOperator]:
    """Map a Python type to its set of supported filter operators."""
    if isinstance(python_type, type):
        for base_type, ops in _TYPE_TO_OPERATORS:
            if issubclass(python_type, base_type):
                return ops
    return _EQ_ONLY


_TYPE_TO_OPENAPI: list[tuple[type, dict[str, Any]]] = [
    (bool, {"type": "boolean"}),
    (datetime, {"type": "string", "format": "date-time"}),
    (UUID, {"type": "string", "format": "uuid"}),
    (int, {"type": "integer"}),
    (float, {"type": "number"}),
    (str, {"type": "string"}),
]


def _python_type_to_openapi_schema(python_type: type) -> dict[str, Any]:
    """Convert a Python type to its OpenAPI schema representation."""
    if isinstance(python_type, type):
        if issubclass(python_type, Enum):
            return {"$ref": f"#/components/schemas/{python_type.__name__}"}
        for base_type, schema in _TYPE_TO_OPENAPI:
            if issubclass(python_type, base_type):
                return schema
    return {"type": "string"}


class FilterableModel:
    """Dependency factory declaring filter query parameters for a list endpoint.

    Introspects ``__filterable_fields__`` and model field types to generate
    OpenAPI filter parameter schemas that match the hand-authored sub-specs.

    Usage::

        @router.get("/items")
        async def list_items(
            _filterable: Annotated[None, Depends(FilterableModel(Item))],
        ) -> ItemListResponse:
            ...
    """

    def __init__(self, model: type) -> None:
        """Validate model metadata and classify field types."""
        filterable_fields: list[str] | None = getattr(model, "__filterable_fields__", None)
        if filterable_fields is None:
            msg = f"{model.__name__} has no __filterable_fields__"
            raise ValueError(msg)

        model_fields_map = getattr(model, "model_fields", {})
        for field_name in filterable_fields:
            if field_name not in model_fields_map:
                msg = (
                    f"{model.__name__}.__filterable_fields__ references "
                    f"'{field_name}' which is not a field on the model"
                )
                raise ValueError(msg)

        self.model = model
        self._fields: dict[str, tuple[set[FilterOperator], type]] = {}

        for field_name in filterable_fields:
            annotation = model_fields_map[field_name].annotation
            python_type = _unwrap_optional(annotation)
            self._fields[field_name] = (_classify_python_type(python_type), python_type)

    def get_field_operators(self, field_name: str) -> set[FilterOperator]:
        """Return the operator set for a given filterable field."""
        return self._fields[field_name][0]

    def to_openapi_params(self) -> list[dict[str, Any]]:
        """Generate deepObject-style OpenAPI parameter dicts for all filterable fields."""
        params: list[dict[str, Any]] = []
        for field_name, (operators, python_type) in self._fields.items():
            base_schema = _python_type_to_openapi_schema(python_type)

            operator_properties: dict[str, Any] = {}
            for op in sorted(operators, key=lambda o: o.value):
                prop: dict[str, Any] = {"title": _OPERATOR_TITLES[op]}
                prop.update(base_schema)
                operator_properties[op.value] = prop

            params.append(
                {
                    "name": field_name,
                    "in": "query",
                    "required": False,
                    "style": "deepObject",
                    "explode": True,
                    "schema": {
                        "allOf": [
                            base_schema,
                            {
                                "type": "object",
                                "properties": operator_properties,
                            },
                        ],
                    },
                }
            )
        return params

    def __call__(self) -> None:  # noqa: D102
        return None
