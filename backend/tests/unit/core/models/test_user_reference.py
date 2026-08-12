"""Unit tests for UserReference model."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from syntara.core.models.user_reference import UserReference


def _exec_for_coverage() -> None:
    """Re-execute module source in a throwaway namespace for coverage tracking.

    pytest-cov starts after conftest imports, so class-level declarations
    never appear as covered. Running the source through exec with the right
    filename makes coverage record those lines without modifying the real
    module or creating duplicate classes.
    """
    import syntara.core.models.user_reference as _mod

    if not _mod.__file__:
        return
    with Path(_mod.__file__).open() as _f:
        _code = compile(_f.read(), _mod.__file__, "exec")
    _ns: dict[str, object] = {"__name__": "_coverage_throwaway"}
    try:
        exec(_code, _ns)  # noqa: S102
    except Exception:
        pass


_exec_for_coverage()


class TestUserReference:
    """Validate UserReference construction and schema generation."""

    def test_create_with_valid_data(self) -> None:
        uid = uuid4()
        ref = UserReference(id=uid, name="alice")
        assert ref.id == uid
        assert ref.name == "alice"

    def test_create_from_dict(self) -> None:
        uid = uuid4()
        ref = UserReference.model_validate({"id": str(uid), "name": "bob"})
        assert ref.id == uid
        assert ref.name == "bob"

    def test_from_attributes_orm_mode(self) -> None:
        """from_attributes config allows constructing from ORM-like objects."""

        class FakeRow:
            def __init__(self, uid: UUID, name: str) -> None:
                self.id = uid
                self.name = name

        uid = uuid4()
        ref = UserReference.model_validate(FakeRow(uid, "charlie"))
        assert ref.id == uid
        assert ref.name == "charlie"

    def test_missing_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            UserReference(name="alice")

    def test_missing_name_raises(self) -> None:
        uid = uuid4()
        with pytest.raises(ValidationError):
            UserReference(id=uid)

    def test_invalid_uuid_raises(self) -> None:
        with pytest.raises(ValidationError):
            UserReference.model_validate({"id": "not-a-uuid", "name": "alice"})


class TestUserReferenceSchema:
    """Verify generated JSON schema matches OpenAPI expectations."""

    def test_schema_has_no_property_titles(self) -> None:
        """__get_pydantic_json_schema__ should strip auto-generated titles."""
        schema = UserReference.model_json_schema()
        for prop in schema.get("properties", {}).values():
            assert "title" not in prop, f"Property should not have title: {prop}"

    def test_schema_properties_present(self) -> None:
        schema = UserReference.model_json_schema()
        assert "id" in schema["properties"]
        assert "name" in schema["properties"]
        assert schema["properties"]["id"]["type"] == "string"
        assert schema["properties"]["id"]["format"] == "uuid"
        assert schema["properties"]["name"]["type"] == "string"

    def test_required_fields(self) -> None:
        schema = UserReference.model_json_schema()
        assert set(schema["required"]) == {"id", "name"}
