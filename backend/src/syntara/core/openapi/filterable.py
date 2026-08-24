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
from typing import Any, Union, get_args, get_origin
from uuid import UUID

from syntara.core.utils.filters import FilterOperator

_STRING_OPS = set(FilterOperator) - {FilterOperator.ISNULL}
_COMPARISON_OPS = _STRING_OPS - {FilterOperator.CONTAINS, FilterOperator.STARTS_WITH}
_EQ_ONLY = {FilterOperator.EQ, FilterOperator.IN}

_OPERATOR_TITLES: dict[FilterOperator, str] = {
    FilterOperator.EQ: "Equals",
    FilterOperator.IN: "In",
    FilterOperator.CONTAINS: "Contains",
    FilterOperator.STARTS_WITH: "Starts With",
    FilterOperator.GT: "Greater Than",
    FilterOperator.GTE: "Greater Than or Equal",
    FilterOperator.LT: "Less Than",
    FilterOperator.LTE: "Less Than or Equal",
    FilterOperator.ISNULL: "Is Null",
}

_OPERATOR_SCHEMA_OVERRIDES: dict[FilterOperator, dict[str, Any]] = {
    FilterOperator.IN: {"type": "string"},
    FilterOperator.ISNULL: {"type": "boolean"},
}


def _unwrap_optional(annotation: Any) -> Any:  # noqa: ANN401
    """Unwrap Optional[X] / X | None to the inner type X."""
    origin = get_origin(annotation)
    if origin is types.UnionType or origin is Union:
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


def _python_type_to_openapi_schema(python_type: type, *, allow_ref: bool = True) -> dict[str, Any]:
    """Convert a Python type to its OpenAPI schema representation."""
    if isinstance(python_type, type):
        if issubclass(python_type, Enum):
            if allow_ref:
                return {"$ref": f"#/components/schemas/{python_type.__name__}"}
            return {"type": "string"}
        for base_type, schema in _TYPE_TO_OPENAPI:
            if issubclass(python_type, base_type):
                return schema
    return {"type": "string"}


class FilterableModel:
    """Dependency factory declaring filter query parameters for a list endpoint.

    Introspects ``__filterable_fields__`` and model field types to generate
    OpenAPI filter parameter schemas that match the hand-authored sub-specs.

    For virtual fields (fields not in ``model_fields``), specify types via
    dict format: ``__filterable_fields__ = {"field": str, "other": datetime}``.
    Regular fields can still use list format for backward compatibility.

    Usage::

        @router.get("/items")
        async def list_items(
            _filterable: Annotated[None, Depends(FilterableModel(Item))],
        ) -> ItemListResponse:
            ...

    Virtual field example::

        class MyModel(SQLModel, table=True):
            __filterable_fields__ = {
                "real_field": str,         # inferred from model, type ignored
                "virtual_field": str,      # virtual field, type used
            }
            real_field: str
            # virtual_field is computed or stored in JSONB
    """

    def __init__(self, model: type) -> None:
        """Validate model metadata and classify field types."""
        filterable_fields_raw = getattr(model, "__filterable_fields__", None)
        if filterable_fields_raw is None:
            msg = f"{model.__name__} has no __filterable_fields__"
            raise ValueError(msg)

        # Support both list[str] and dict[str, type] formats
        if isinstance(filterable_fields_raw, dict):
            filterable_fields: dict[str, type | None] = filterable_fields_raw
        else:
            # Convert list to dict with None as type (will be inferred)
            filterable_fields = {name: None for name in filterable_fields_raw}

        model_fields_map = getattr(model, "model_fields", {})

        self.model = model
        self._fields: dict[str, tuple[set[FilterOperator], type]] = {}

        for field_name, declared_type in filterable_fields.items():
            # Try to get type from model_fields first
            if field_name in model_fields_map:
                annotation = model_fields_map[field_name].annotation
                python_type = _unwrap_optional(annotation)
                ops = _classify_python_type(python_type)
                if python_type is not annotation:
                    ops = ops | {FilterOperator.ISNULL}
                self._fields[field_name] = (ops, python_type)
            # Fall back to declared type for virtual fields
            elif declared_type is not None:
                python_type = declared_type
                ops = _classify_python_type(python_type)
                self._fields[field_name] = (ops, python_type)
            # Error if field is not found and has no declared type
            else:
                msg = (
                    f"Field '{field_name}' in {model.__name__}.__filterable_fields__ "
                    f"not found in model_fields. For virtual fields, use dict format: "
                    f"__filterable_fields__ = {{'{field_name}': <type>}}"
                )
                raise ValueError(msg)

    def get_field_operators(self, field_name: str) -> set[FilterOperator]:
        """Return the operator set for a given filterable field."""
        return self._fields[field_name][0]

    def to_openapi_params(self) -> list[dict[str, Any]]:
        """Generate deepObject-style OpenAPI parameter dicts for all filterable fields."""
        params: list[dict[str, Any]] = []
        for field_name, (operators, python_type) in self._fields.items():
            base_schema = _python_type_to_openapi_schema(python_type)
            op_schema = _python_type_to_openapi_schema(python_type, allow_ref=False)

            operator_properties: dict[str, Any] = {}
            for op in sorted(operators, key=lambda o: o.value):
                title = _OPERATOR_TITLES.get(op, op.value.replace("_", " ").title())
                prop: dict[str, Any] = {"title": title}
                prop.update(_OPERATOR_SCHEMA_OVERRIDES.get(op, op_schema))
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
