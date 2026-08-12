"""Unit tests for WorkflowVersionUpdate schema."""

import pytest
from pydantic import ValidationError

from syntara.workflows.models.workflow_version import WorkflowVersionUpdate


class TestWorkflowVersionUpdate:
    """Test WorkflowVersionUpdate request schema."""

    def test_valid_with_both_fields(self) -> None:
        update = WorkflowVersionUpdate(name="Release 1.0", change_description="First release")
        assert update.name == "Release 1.0"
        assert update.change_description == "First release"

    def test_valid_with_only_name(self) -> None:
        update = WorkflowVersionUpdate(name="Release 1.0")
        assert update.name == "Release 1.0"
        assert update.change_description is None
        assert update.model_fields_set == {"name"}

    def test_valid_with_only_change_description(self) -> None:
        update = WorkflowVersionUpdate(change_description="Bug fix")
        assert update.change_description == "Bug fix"
        assert update.name is None
        assert update.model_fields_set == {"change_description"}

    def test_valid_empty_body(self) -> None:
        update = WorkflowVersionUpdate()
        assert update.name is None
        assert update.change_description is None
        assert update.model_fields_set == set()

    def test_explicit_null_values(self) -> None:
        update = WorkflowVersionUpdate(name=None, change_description=None)
        assert update.name is None
        assert update.change_description is None
        assert update.model_fields_set == {"name", "change_description"}

    def test_name_max_length(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 255 characters"):
            WorkflowVersionUpdate(name="x" * 256)

    def test_change_description_max_length(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 1024 characters"):
            WorkflowVersionUpdate(change_description="x" * 1025)

    def test_name_at_max_length(self) -> None:
        update = WorkflowVersionUpdate(name="x" * 255)
        assert update.name is not None
        assert len(update.name) == 255

    def test_change_description_at_max_length(self) -> None:
        update = WorkflowVersionUpdate(change_description="x" * 1024)
        assert update.change_description is not None
        assert len(update.change_description) == 1024

    def test_model_fields_set_tracks_sent_fields(self) -> None:
        update = WorkflowVersionUpdate.model_validate({"name": "Name"})
        assert "name" in update.model_fields_set
        assert "change_description" not in update.model_fields_set
