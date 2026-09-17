"""Unit tests for credential model schemas — CredentialRead with UserReference."""

from uuid import uuid4

from syntara.core.models.user_reference import UserReference
from syntara.credentials.models.credential import (
    CredentialCreate,
    CredentialRead,
    CredentialUpdate,
    CredentialWorkflowRef,
)


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
        assert ref.created_at is None
