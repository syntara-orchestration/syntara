"""Unit tests for credential model schemas — CredentialRead with UserReference."""

from pathlib import Path
from uuid import uuid4

from syntara.core.models.user_reference import UserReference
from syntara.credentials.models.credential import (
    CredentialCreate,
    CredentialRead,
    CredentialUpdate,
    CredentialWorkflowRef,
)


def _exec_for_coverage() -> None:
    """Re-execute module source in a throwaway namespace for coverage tracking.

    ``pytest-cov`` starts *after* conftest imports, so class-level
    declarations never appear as covered.  Running the source through
    ``exec`` with the correct filename records those lines without
    modifying real module objects.

    For modules containing ``table=True`` SQLModel classes we redirect
    table registration to a throwaway MetaData so the real registry is
    never touched.
    """
    import warnings
    from unittest.mock import patch

    import sqlalchemy as sa

    import syntara.credentials.models.credential as _mod
    import syntara.credentials.models.credential_type as _ct_mod

    scratch_meta = sa.MetaData()

    for mod in (_ct_mod, _mod):
        if not mod.__file__:
            continue
        with Path(mod.__file__).open() as _f:
            _code = compile(_f.read(), mod.__file__, "exec")
        try:
            with warnings.catch_warnings(), patch("sqlmodel.main.SQLModel.metadata", scratch_meta):
                warnings.simplefilter("ignore")
                exec(_code, {"__name__": "_coverage_throwaway"})  # noqa: S102
        except Exception:
            pass


_exec_for_coverage()


class TestCredentialRead:
    """Verify CredentialRead handles UserReference fields correctly."""

    def test_accepts_user_reference_objects(self) -> None:
        uid = uuid4()
        UserReference(id=uid, name="alice")
        read = CredentialRead.model_validate(
            {
                "id": str(uuid4()),
                "name": "test-cred",
                "credential_type_id": str(uuid4()),
                "project_id": str(uuid4()),
                "created_by": {"id": str(uid), "name": "alice"},
                "updated_by": {"id": str(uid), "name": "alice"},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "labels": {},
            },
        )
        assert isinstance(read.created_by, UserReference)
        assert read.created_by.name == "alice"
        assert isinstance(read.updated_by, UserReference)

    def test_accepts_raw_uuid_string_for_created_by(self) -> None:
        uid = uuid4()
        read = CredentialRead.model_validate(
            {
                "id": str(uuid4()),
                "name": "test-cred",
                "credential_type_id": str(uuid4()),
                "project_id": str(uuid4()),
                "created_by": str(uid),
                "updated_by": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "labels": {},
            },
        )
        assert str(read.created_by) == str(uid)

    def test_accepts_null_user_fields(self) -> None:
        read = CredentialRead.model_validate(
            {
                "id": str(uuid4()),
                "name": "test-cred",
                "credential_type_id": str(uuid4()),
                "project_id": str(uuid4()),
                "created_by": None,
                "updated_by": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "labels": {},
            },
        )
        assert read.created_by is None
        assert read.updated_by is None

    def test_schema_extras_set_readonly(self) -> None:
        extras = CredentialRead.FIELD_SCHEMA_EXTRAS
        assert extras["created_by"]["readOnly"] is True
        assert extras["updated_by"]["readOnly"] is True

    def test_schema_extras_restrict_anyof_to_user_reference_or_null(self) -> None:
        """FIELD_SCHEMA_EXTRAS should restrict anyOf to UserReference | null only."""
        any_of = CredentialRead.FIELD_SCHEMA_EXTRAS["created_by"]["anyOf"]
        refs = [item.get("$ref") for item in any_of if "$ref" in item]
        types = [item.get("type") for item in any_of if "type" in item]
        assert "#/components/schemas/UserReference" in refs
        assert "null" in types
        assert "string" not in types
        assert len(any_of) == 2


class TestCredentialCreate:
    """Basic coverage for CredentialCreate model."""

    def test_create_with_required_fields(self) -> None:
        data = CredentialCreate(
            name="test",
            credential_type_id=uuid4(),
            inputs={"token": "abc"},
            project_id=uuid4(),
        )
        assert data.name == "test"


class TestCredentialUpdate:
    """Basic coverage for CredentialUpdate model."""

    def test_all_fields_optional(self) -> None:
        update = CredentialUpdate()
        assert update.name is None
        assert update.inputs is None


class TestCredentialWorkflowRef:
    """Basic coverage for CredentialWorkflowRef model."""

    def test_create_ref(self) -> None:
        ref = CredentialWorkflowRef(id=uuid4(), name="my-workflow")
        assert ref.name == "my-workflow"
        assert ref.node_names == []
