"""Unit tests for credential model schemas — CredentialRead with UserReference."""

from uuid import uuid4

from syntara.core.models.user_reference import UserReference, UserReferenceType
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
        UserReference(id=uid, name="alice", type=UserReferenceType.USER)
        read = CredentialRead.model_validate(
            {
                "id": str(uuid4()),
                "name": "test-cred",
                "credential_type_id": str(uuid4()),
                "project_id": str(uuid4()),
                "created_by": {"id": str(uid), "name": "alice", "type": "user"},
                "updated_by": {"id": str(uid), "name": "alice", "type": "user"},
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

    def test_declares_its_user_reference_fields(self) -> None:
        """The shared resolver reads this declaration to know what to populate."""
        assert CredentialRead.USER_REFERENCE_FIELDS == ("created_by", "updated_by")

    def test_user_reference_fields_are_advertised_as_reference_or_null(self) -> None:
        """UserReferenceFieldsMixin narrows the field to UserReference | null, readOnly.

        Without it the ``UserReference | UUID | str | None`` annotation would leak a
        four-way union into the OpenAPI spec.
        """
        spec = UserReference.OPENAPI_NULLABLE_FIELD
        assert spec["readOnly"] is True
        refs = [item.get("$ref") for item in spec["anyOf"] if "$ref" in item]
        types = [item.get("type") for item in spec["anyOf"] if "type" in item]
        assert "#/components/schemas/UserReference" in refs
        assert "null" in types
        assert "string" not in types
        assert len(spec["anyOf"]) == 2


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
