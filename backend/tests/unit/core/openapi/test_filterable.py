"""Tests for FilterableModel dependency factory.

Tests verify that FilterableModel correctly introspects model metadata
to classify field types and generate appropriate operator sets for
OpenAPI filter param schemas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import ClassVar
from uuid import UUID

import pytest
from sqlmodel import Field, SQLModel

from syntara.core.openapi.filterable import _COMPARISON_OPS, _EQ_ONLY, _STRING_OPS
from syntara.core.utils.filters import FilterOperator


class SampleStatus(str, Enum):  # noqa: D101
    ACTIVE = "active"
    INACTIVE = "inactive"


class SampleModel(SQLModel, table=False):
    """Test model with representative field types."""

    id: UUID = Field(default=None)
    name: str = Field(default="")
    description: str | None = Field(default=None)
    status: SampleStatus = Field(default=SampleStatus.ACTIVE)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default=None)
    score: int = Field(default=0)
    rating: float = Field(default=0.0)

    __filterable_fields__: ClassVar[list[str]] = [
        "id",
        "name",
        "description",
        "status",
        "enabled",
        "created_at",
    ]


@pytest.mark.unit
class TestOperatorTitlesCoverage:
    """Ensure every FilterOperator has a title for spec generation."""

    def test_all_operators_have_titles(self):
        from syntara.core.openapi.filterable import _OPERATOR_TITLES

        missing = set(FilterOperator) - set(_OPERATOR_TITLES)
        assert not missing, f"Missing titles for operators: {missing}"


@pytest.mark.unit
class TestClassifyPythonType:
    """Test type classification for operator set inference."""

    @pytest.mark.parametrize(
        ("python_type", "expected_ops"),
        [
            (str, _STRING_OPS),
            (datetime, _COMPARISON_OPS),
            (UUID, _EQ_ONLY),
            (bool, _EQ_ONLY),
            (SampleStatus, _EQ_ONLY),
            (int, _COMPARISON_OPS),
            (float, _COMPARISON_OPS),
        ],
        ids=["string", "datetime", "uuid", "bool", "enum", "int", "float"],
    )
    def test_type_classification(self, python_type, expected_ops):
        from syntara.core.openapi.filterable import _classify_python_type

        assert _classify_python_type(python_type) == expected_ops


@pytest.mark.unit
class TestUnwrapOptional:
    """Test optional type unwrapping."""

    def test_plain_type(self):
        from syntara.core.openapi.filterable import _unwrap_optional

        assert _unwrap_optional(str) is str

    def test_optional_type(self):
        from syntara.core.openapi.filterable import _unwrap_optional

        assert _unwrap_optional(str | None) is str

    def test_optional_uuid(self):
        from syntara.core.openapi.filterable import _unwrap_optional

        assert _unwrap_optional(UUID | None) is UUID

    def test_typing_optional(self):
        from syntara.core.openapi.filterable import _unwrap_optional

        assert _unwrap_optional(str | None) is str

    def test_typing_optional_uuid(self):
        from syntara.core.openapi.filterable import _unwrap_optional

        assert _unwrap_optional(UUID | None) is UUID


@pytest.mark.unit
class TestFilterableModel:
    """Test FilterableModel dependency factory."""

    def test_has_model_attribute(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        assert dep.model is SampleModel

    def test_is_callable(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        assert callable(dep)

    def test_call_returns_none(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        result = dep()
        assert result is None

    def test_rejects_model_without_filterable_fields(self):
        from syntara.core.openapi.filterable import FilterableModel

        class NoFilterModel(SQLModel, table=False):
            name: str = ""

        with pytest.raises(ValueError, match="__filterable_fields__"):
            FilterableModel(NoFilterModel)

    def test_raises_error_for_undeclared_virtual_field(self):
        """Field in list-format __filterable_fields__ but not in model_fields should error (use dict format for virtual fields)."""
        from syntara.core.openapi.filterable import FilterableModel

        class VirtualFieldModel(SQLModel, table=False):
            name: str = ""
            __filterable_fields__: ClassVar[list[str]] = ["name", "nonexistent"]

        with pytest.raises(ValueError, match=r"nonexistent.*not found"):
            FilterableModel(VirtualFieldModel)

    def test_virtual_field_with_type_declaration(self):
        """Virtual fields with types in dict-format __filterable_fields__ should be included."""
        from syntara.core.openapi.filterable import FilterableModel

        class VirtualFieldModel(SQLModel, table=False):
            name: str = ""
            __filterable_fields__: ClassVar[dict[str, type | None]] = {
                "name": None,  # Will be inferred from model_fields
                "virtual_field": str,  # Virtual field with explicit type
            }

        dep = FilterableModel(VirtualFieldModel)
        assert "name" in dep._fields
        assert "virtual_field" in dep._fields
        assert dep.get_field_operators("virtual_field") == _STRING_OPS

    def test_operators_for_string_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        ops = dep.get_field_operators("name")
        assert ops == _STRING_OPS

    def test_operators_for_optional_string_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        ops = dep.get_field_operators("description")
        assert ops == _STRING_OPS | {FilterOperator.ISNULL}

    def test_operators_for_datetime_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        ops = dep.get_field_operators("created_at")
        assert ops == _COMPARISON_OPS

    def test_operators_for_uuid_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        ops = dep.get_field_operators("id")
        assert ops == _EQ_ONLY

    def test_operators_for_bool_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        ops = dep.get_field_operators("enabled")
        assert ops == _EQ_ONLY

    def test_operators_for_enum_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        ops = dep.get_field_operators("status")
        assert ops == _EQ_ONLY


@pytest.mark.unit
class TestPythonTypeToOpenAPISchema:
    """Test Python-to-OpenAPI type mapping."""

    @pytest.mark.parametrize(
        ("python_type", "expected_schema"),
        [
            (str, {"type": "string"}),
            (datetime, {"type": "string", "format": "date-time"}),
            (UUID, {"type": "string", "format": "uuid"}),
            (bool, {"type": "boolean"}),
            (int, {"type": "integer"}),
            (float, {"type": "number"}),
            (SampleStatus, {"$ref": "#/components/schemas/SampleStatus"}),
        ],
        ids=["string", "datetime", "uuid", "bool", "int", "float", "enum"],
    )
    def test_type_mapping(self, python_type, expected_schema):
        from syntara.core.openapi.filterable import _python_type_to_openapi_schema

        assert _python_type_to_openapi_schema(python_type) == expected_schema


@pytest.mark.unit
class TestToOpenAPIParams:
    """Test deepObject-style OpenAPI parameter generation."""

    def test_returns_one_param_per_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        param_names = {p["name"] for p in params}

        for field_name in SampleModel.__filterable_fields__:
            assert field_name in param_names, f"Expected filter param '{field_name}' in OpenAPI params"

    def test_param_structure(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        name_param = next(p for p in params if p["name"] == "name")

        assert name_param["in"] == "query"
        assert name_param["required"] is False
        assert name_param["style"] == "deepObject"
        assert name_param["explode"] is True
        assert "schema" in name_param
        assert "allOf" in name_param["schema"]
        assert len(name_param["schema"]["allOf"]) == 2

    def test_string_field_operators(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        name_param = next(p for p in params if p["name"] == "name")

        operator_obj = name_param["schema"]["allOf"][1]
        assert operator_obj["type"] == "object"
        props = operator_obj["properties"]

        expected_ops = {op.value for op in _STRING_OPS}
        assert set(props.keys()) == expected_ops

        assert props["eq"]["title"] == "Equals"
        assert props["eq"]["type"] == "string"
        assert props["contains"]["title"] == "Contains"
        assert props["starts_with"]["title"] == "Starts With"

    def test_string_field_base_schema(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        name_param = next(p for p in params if p["name"] == "name")

        base_schema = name_param["schema"]["allOf"][0]
        assert base_schema == {"type": "string"}

    def test_uuid_field_has_eq_only(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        id_param = next(p for p in params if p["name"] == "id")

        operator_obj = id_param["schema"]["allOf"][1]
        assert set(operator_obj["properties"].keys()) == {"eq", "in"}
        assert operator_obj["properties"]["eq"]["type"] == "string"
        assert operator_obj["properties"]["eq"]["format"] == "uuid"

    def test_uuid_field_base_schema(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        id_param = next(p for p in params if p["name"] == "id")

        base_schema = id_param["schema"]["allOf"][0]
        assert base_schema == {"type": "string", "format": "uuid"}

    def test_bool_field_operators(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        enabled_param = next(p for p in params if p["name"] == "enabled")

        operator_obj = enabled_param["schema"]["allOf"][1]
        assert set(operator_obj["properties"].keys()) == {"eq", "in"}
        assert operator_obj["properties"]["eq"]["type"] == "boolean"

    def test_datetime_field_operators(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        created_at_param = next(p for p in params if p["name"] == "created_at")

        operator_obj = created_at_param["schema"]["allOf"][1]
        expected_ops = {op.value for op in _COMPARISON_OPS}
        assert set(operator_obj["properties"].keys()) == expected_ops

        assert operator_obj["properties"]["gt"]["type"] == "string"
        assert operator_obj["properties"]["gt"]["format"] == "date-time"
        assert operator_obj["properties"]["gt"]["title"] == "Greater Than"

    def test_enum_field_uses_ref(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        status_param = next(p for p in params if p["name"] == "status")

        base_schema = status_param["schema"]["allOf"][0]
        assert base_schema == {"$ref": "#/components/schemas/SampleStatus"}

        operator_obj = status_param["schema"]["allOf"][1]
        assert set(operator_obj["properties"].keys()) == {"eq", "in"}
        assert operator_obj["properties"]["eq"]["type"] == "string"
        assert operator_obj["properties"]["eq"]["title"] == "Equals"
        assert "$ref" not in operator_obj["properties"]["eq"]

    def test_optional_field_adds_isnull(self):
        """Optional field should have isnull operator; non-optional should not."""
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        name_param = next(p for p in params if p["name"] == "name")
        desc_param = next(p for p in params if p["name"] == "description")

        name_ops = name_param["schema"]["allOf"][1]["properties"]
        desc_ops = desc_param["schema"]["allOf"][1]["properties"]

        assert "isnull" not in name_ops
        assert "isnull" in desc_ops
        assert set(desc_ops.keys()) == set(name_ops.keys()) | {"isnull"}
        assert name_param["schema"]["allOf"][0] == desc_param["schema"]["allOf"][0]


@pytest.mark.unit
class TestInAndIsnullSchemas:
    """Test that IN and ISNULL operators generate correct schema types."""

    def test_in_operator_uses_string_type_for_string_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        name_param = next(p for p in params if p["name"] == "name")

        op_props = name_param["schema"]["allOf"][1]["properties"]
        assert "in" in op_props
        assert op_props["in"]["type"] == "string"
        assert op_props["in"]["title"] == "In"

    def test_in_operator_ignores_uuid_base_schema(self):
        """IN should always be string type, not inherit the field's UUID format."""
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        id_param = next(p for p in params if p["name"] == "id")

        op_props = id_param["schema"]["allOf"][1]["properties"]
        assert op_props["in"]["type"] == "string"
        assert "format" not in op_props["in"]

    def test_isnull_uses_boolean_for_optional_field(self):
        """ISNULL should always be boolean, not inherit the field's type."""
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        desc_param = next(p for p in params if p["name"] == "description")

        op_props = desc_param["schema"]["allOf"][1]["properties"]
        assert "isnull" in op_props
        assert op_props["isnull"]["type"] == "boolean"
        assert op_props["isnull"]["title"] == "Is Null"

    def test_isnull_absent_for_non_optional_field(self):
        from syntara.core.openapi.filterable import FilterableModel

        dep = FilterableModel(SampleModel)
        params = dep.to_openapi_params()
        name_param = next(p for p in params if p["name"] == "name")

        op_props = name_param["schema"]["allOf"][1]["properties"]
        assert "isnull" not in op_props


@pytest.mark.unit
class TestFilterableModelInjection:
    """Test that FilterableModel params are injected into FastAPI spec via export script."""

    def test_inject_filter_params_adds_to_spec(self):
        """_inject_filter_params should add deepObject params to spec operations."""
        from fastapi import Depends, FastAPI

        from syntara.core.openapi.filterable import FilterableModel

        app = FastAPI()

        @app.get("/items")  # type: ignore[misc]
        async def list_items(
            _filterable: None = Depends(FilterableModel(SampleModel)),  # noqa: FAST002
        ) -> list:
            return []

        spec = app.openapi()

        from tools.export_openapi import _inject_filter_params

        _inject_filter_params(app, spec)

        params = spec["paths"]["/items"]["get"].get("parameters", [])
        param_names = {p["name"] for p in params}

        for field_name in SampleModel.__filterable_fields__:
            assert field_name in param_names, (
                f"Expected filter param '{field_name}' in OpenAPI spec parameters after injection"
            )

    def test_inject_filter_params_deepobject_style(self):
        """Injected params should use deepObject style."""
        from fastapi import Depends, FastAPI

        from syntara.core.openapi.filterable import FilterableModel

        app = FastAPI()

        @app.get("/items")  # type: ignore[misc]
        async def list_items(
            _filterable: None = Depends(FilterableModel(SampleModel)),  # noqa: FAST002
        ) -> list:
            return []

        spec = app.openapi()

        from tools.export_openapi import _inject_filter_params

        _inject_filter_params(app, spec)

        params = spec["paths"]["/items"]["get"]["parameters"]
        name_param = next(p for p in params if p["name"] == "name")

        assert name_param["style"] == "deepObject"
        assert name_param["explode"] is True
        assert "allOf" in name_param["schema"]

    def test_inject_does_not_duplicate_existing_params(self):
        """If a param name already exists, injection should not add a duplicate."""
        from fastapi import Depends, FastAPI

        from syntara.core.openapi.filterable import FilterableModel

        app = FastAPI()

        @app.get("/items")  # type: ignore[misc]
        async def list_items(
            _filterable: None = Depends(FilterableModel(SampleModel)),  # noqa: FAST002
        ) -> list:
            return []

        spec = app.openapi()

        from tools.export_openapi import _inject_filter_params

        _inject_filter_params(app, spec)
        _inject_filter_params(app, spec)

        params = spec["paths"]["/items"]["get"]["parameters"]
        name_params = [p for p in params if p["name"] == "name"]
        assert len(name_params) == 1

    def test_no_injection_without_filterable_model(self):
        """Routes without FilterableModel should not get filter params."""
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/plain")  # type: ignore[misc]
        async def plain() -> list:
            return []

        spec = app.openapi()

        from tools.export_openapi import _inject_filter_params

        _inject_filter_params(app, spec)

        params = spec["paths"]["/plain"]["get"].get("parameters", [])
        deepobject_params = [p for p in params if p.get("style") == "deepObject"]
        assert deepobject_params == []
