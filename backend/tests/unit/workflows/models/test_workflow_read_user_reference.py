"""Unit tests for WorkflowRead UserReference fields."""

from datetime import UTC, datetime
from uuid import uuid4

from syntara.core.models.user_reference import UserReference
from syntara.workflows.models.workflow import WorkflowRead


class TestWorkflowReadUserReference:
    """Verify WorkflowRead handles UserReference fields correctly."""

    def test_accepts_user_reference_objects(self) -> None:
        uid = uuid4()
        updater = uuid4()
        read = WorkflowRead(
            name="wf",
            id=uuid4(),
            current_version=1,
            is_enabled=False,
            created_by=UserReference(id=uid, name="alice"),
            updated_by=UserReference(id=updater, name="bob"),
            project_id=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert isinstance(read.created_by, UserReference)
        assert read.created_by.name == "alice"
        assert isinstance(read.updated_by, UserReference)
        assert read.updated_by.name == "bob"

    def test_accepts_uuid_and_none(self) -> None:
        uid = uuid4()
        read = WorkflowRead(
            name="wf",
            id=uuid4(),
            current_version=1,
            is_enabled=False,
            created_by=uid,
            updated_by=None,
            project_id=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert read.created_by == uid
        assert read.updated_by is None

    def test_field_schema_extras_reference_user_reference(self) -> None:
        refs = [
            item.get("$ref", "")
            for schema in WorkflowRead.FIELD_SCHEMA_EXTRAS.values()
            for item in schema.get("anyOf", [])
            if isinstance(item, dict)
        ]
        assert "#/components/schemas/UserReference" in refs
