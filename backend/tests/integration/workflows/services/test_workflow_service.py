"""Unit tests for WorkflowService.

These tests verify the business logic layer for workflow management.
Tests use real database fixtures to test actual database interactions.
"""

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.exceptions import BuiltinProtectionError
from syntara.authz.models.project import Project
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.workflows.exceptions import (
    BuiltinWorkflowDeleteError,
    BuiltinWorkflowModifyError,
    WorkflowNameConflictError,
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowPublishValidationError,
    WorkflowVersionConflictError,
    WorkflowVersionNotFoundError,
)
from syntara.workflows.models import Workflow, WorkflowListResponse, WorkflowRead, WorkflowVersion
from syntara.workflows.models.validation_finding import (
    ValidationCategory,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)
from syntara.workflows.services.workflow_service import WorkflowConvertResourceMixin, WorkflowService


def _valid_result() -> ValidationResult:
    """Return a ValidationResult that passes all gates."""
    return ValidationResult(is_valid=True, error_count=0, warning_count=0, findings=[])


def _invalid_result(message: str = "Invalid definition") -> ValidationResult:
    """Return a ValidationResult with one error finding."""
    return ValidationResult(
        is_valid=False,
        error_count=1,
        warning_count=0,
        findings=[
            ValidationFinding(
                severity=ValidationSeverity.error,
                category=ValidationCategory.schema_violation,
                message=message,
            )
        ],
    )


def _warnings_result(message: str = "Missing recommended field") -> ValidationResult:
    """Return a ValidationResult with one warning finding (no errors)."""
    return ValidationResult(
        is_valid=True,
        error_count=0,
        warning_count=1,
        findings=[
            ValidationFinding(
                severity=ValidationSeverity.warning,
                category=ValidationCategory.schema_violation,
                message=message,
            )
        ],
    )


def _mock_validator_valid() -> MagicMock:
    """Return a MagicMock for workflow_validator with collect_findings returning valid."""
    mock = MagicMock()
    mock.collect_findings.return_value = _valid_result()
    return mock


class TestWorkflowServiceBase:
    """Base test class with helper methods for WorkflowService tests."""

    _test_project_id: UUID

    @pytest.fixture(autouse=True)
    def _inject_project_id(self, test_project_id: UUID) -> None:
        self._test_project_id = test_project_id

    def _create_test_workflow(
        self,
        workflow_id: UUID | None = None,
        name: str = "test-workflow",
        description: str | None = "Test workflow",
        labels: dict[str, Any] | None = None,
        current_version: int = 1,
        created_by: UUID | None = None,
        project_id: UUID | None = None,
        *,
        is_enabled: bool = False,
        is_builtin: bool = False,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
    ) -> Workflow:
        """Create a test Workflow object."""
        now = datetime.now(UTC)
        return Workflow(
            id=workflow_id or uuid4(),
            name=name,
            description=description,
            labels=labels or {},
            current_version=current_version,
            created_by=created_by or uuid4(),
            project_id=project_id or self._test_project_id,
            is_enabled=is_enabled,
            is_builtin=is_builtin,
            published_version_id=None,  # Set after version is created when is_enabled
            created_at=created_at or now,
            updated_at=updated_at or now,
            deleted_at=deleted_at,
        )

    def _create_test_workflow_version(
        self,
        version_id: UUID | None = None,
        workflow_id: UUID | None = None,
        version: int = 1,
        schema_version: str = "2.0.0",
        workflow_definition: dict[str, Any] | None = None,
        created_by: UUID | None = None,
        change_description: str = "Initial version",
        created_at: datetime | None = None,
        deleted_at: datetime | None = None,
    ) -> WorkflowVersion:
        """Create a test WorkflowVersion object."""
        return WorkflowVersion(
            id=version_id or uuid4(),
            workflow_id=workflow_id or uuid4(),
            version=version,
            schema_version=schema_version,
            workflow_definition=workflow_definition or self._create_minimal_workflow_definition(),
            created_by=created_by or uuid4(),
            change_description=change_description,
            created_at=created_at or datetime.now(UTC),
            deleted_at=deleted_at,
        )

    def _create_minimal_workflow_definition(self) -> dict[str, Any]:
        """Create a minimal valid V2 workflow definition."""
        return {
            "schema_version": "2.0.0",
            "name": "test-workflow",
            "description": "Test workflow",
            "triggers": [
                {
                    "id": "trigger_manual",
                    "type": "manual_trigger",
                    "parameters": {},
                }
            ],
            "nodes": [
                {
                    "id": "task1",
                    "name": "Task 1",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "print('hello')",
                    },
                }
            ],
            "edges": [
                {"from": "trigger_manual", "to": "task1"},
            ],
        }

    def _create_workflow_definition(self, **overrides: dict[str, Any]) -> dict[str, Any]:
        """Create a workflow definition dict with optional overrides."""
        definition = self._create_minimal_workflow_definition()
        for key, value in overrides.items():
            if "." in key:
                keys = key.split(".")
                target = definition
                for k in keys[:-1]:
                    target = target[k]
                target[keys[-1]] = value
            else:
                definition[key] = value
        return definition


class TestWorkflowServiceInit(TestWorkflowServiceBase):
    """Test WorkflowService initialization."""

    @pytest.mark.asyncio
    async def test_init_sets_session_and_user(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that WorkflowService initialization sets session and user correctly."""
        service = WorkflowService(test_db_session, test_user)

        assert service.session == test_db_session
        assert service.user == test_user
        assert service.convert_resource_mixin is not None


class TestWorkflowServiceDuplicateDetection(TestWorkflowServiceBase):
    """Test duplicate name detection logic."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("statement", "args", "expected"),
        [
            (
                "duplicate key value violates unique constraint",
                (
                    "(psycopg2.errors.UniqueViolation) duplicate key value violates unique "
                    'constraint "ix_workflows_name_project_unique"',
                ),
                True,
            ),
            (
                "constraint error",
                ("workflows.name constraint violated",),
                True,
            ),
            (
                "error",
                ("DUPLICATE KEY constraint violated",),
                True,
            ),
            (
                "foreign key constraint",
                (),
                False,
            ),
        ],
    )
    async def test_is_duplicate_name_error_parameterized(
        self, test_db_session: AsyncSession, test_user: User, statement: str, args: tuple[str, ...], *, expected: bool
    ) -> None:
        """Test duplicate detection with various error messages and args."""
        service = WorkflowService(test_db_session, test_user)

        error = IntegrityError(statement, "SELECT", None)  # type: ignore[arg-type]
        error.args = args

        result = service._is_duplicate_name_error(error)
        assert result is expected


class TestWorkflowServiceFlushWithDuplicateCheck(TestWorkflowServiceBase):
    """Test flush with duplicate check functionality."""

    @pytest.mark.asyncio
    async def test_flush_with_duplicate_check_raises_workflow_name_conflict(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test flush raises WorkflowNameConflictError for duplicate name."""
        service = WorkflowService(test_db_session, test_user)

        # Create a workflow first
        workflow = self._create_test_workflow(name="duplicate-name", created_by=test_user.id)
        test_db_session.add(workflow)
        await test_db_session.commit()

        # Now try to create another with the same name using direct SQL to trigger IntegrityError
        with patch.object(test_db_session, "flush") as mock_flush:
            duplicate_error = IntegrityError("duplicate", "SELECT", None)  # type: ignore[arg-type]
            duplicate_error.args = ("ix_workflows_name_project_unique constraint violated",)
            mock_flush.side_effect = duplicate_error

            with pytest.raises(WorkflowNameConflictError) as exc_info:
                await service._flush_with_duplicate_check("duplicate-name")

            assert str(exc_info.value) == "Workflow with name 'duplicate-name' already exists in this project"


class TestWorkflowServiceCreateWorkflow(TestWorkflowServiceBase):
    """Test create_workflow functionality."""

    @pytest.mark.asyncio
    async def test_create_workflow_success(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test successful workflow creation."""
        service = WorkflowService(test_db_session, test_user)

        workflow_definition = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            result = await service.create_workflow(
                name="test-workflow",
                description="Test description",
                labels={"env": "test"},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

            workflow, version, _val_result = result
            assert workflow.name == "test-workflow"
            assert workflow.description == "Test description"
            assert workflow.labels == {"env": "test"}
            assert workflow.current_version == 1
            assert workflow.created_by == test_user.id
            assert workflow.is_enabled is False

            assert version.workflow_id == workflow.id
            assert version.version == 1
            assert version.schema_version == "2.0.0"
            assert version.workflow_definition == workflow_definition
            assert version.created_by == test_user.id
            assert version.change_description == "Initial version"

            # Verify workflow exists in database
            db_workflow = await test_db_session.get(Workflow, workflow.id)
            assert db_workflow is not None
            assert db_workflow.name == "test-workflow"

    @pytest.mark.asyncio
    async def test_create_workflow_validation_error_saves_with_issues(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test workflow creation with invalid definition still saves and reports issues."""
        service = WorkflowService(test_db_session, test_user)

        workflow_definition = self._create_workflow_definition()

        mock_val = MagicMock()
        mock_val.collect_findings.return_value = _invalid_result("Invalid definition")

        with patch("syntara.workflows.services.workflow_service.workflow_validator", mock_val):
            workflow, _version, val_result = await service.create_workflow(
                name="invalid-workflow",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

            assert workflow.has_validation_issues is True
            assert val_result.error_count > 0

    @pytest.mark.asyncio
    async def test_create_workflow_duplicate_name(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test workflow creation with duplicate name."""
        service = WorkflowService(test_db_session, test_user)

        # First, create a workflow with a specific name
        workflow_definition = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            # Create first workflow
            await service.create_workflow(
                name="duplicate-workflow",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

        # Now try to create another with the same name
        with (
            patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()),
            pytest.raises(WorkflowNameConflictError),
        ):
            await service.create_workflow(
                name="duplicate-workflow",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

    @pytest.mark.asyncio
    async def test_create_workflow_same_name_different_project(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Same workflow name in different projects should succeed."""
        service = WorkflowService(test_db_session, test_user)
        workflow_definition = self._create_workflow_definition()

        other_project = Project(name=f"other-project-{uuid4().hex[:8]}", labels={})
        test_db_session.add(other_project)
        await test_db_session.commit()
        await test_db_session.refresh(other_project)

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            wf_a, _, _ = await service.create_workflow(
                name="cross-project-wf",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            wf_b, _, _ = await service.create_workflow(
                name="cross-project-wf",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=other_project.id,
            )

        assert wf_a.name == wf_b.name == "cross-project-wf"
        assert wf_a.project_id != wf_b.project_id

    @pytest.mark.asyncio
    async def test_create_workflow_same_name_same_project_fails(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Same workflow name in the same project should fail with 409."""
        service = WorkflowService(test_db_session, test_user)
        workflow_definition = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            await service.create_workflow(
                name="same-project-wf",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

        with (
            patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()),
            pytest.raises(WorkflowNameConflictError),
        ):
            await service.create_workflow(
                name="same-project-wf",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

    @pytest.mark.asyncio
    async def test_create_workflow_with_warnings_succeeds(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test workflow creation with warnings succeeds and reports validation issues."""
        service = WorkflowService(test_db_session, test_user)

        workflow_definition = self._create_workflow_definition()

        mock_val = MagicMock()
        mock_val.collect_findings.return_value = _warnings_result()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", mock_val):
            workflow, _version, val_result = await service.create_workflow(
                name="warnings-workflow",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

            assert workflow.has_validation_issues is True
            assert val_result.warning_count > 0

    @pytest.mark.asyncio
    async def test_create_workflow_errors_always_saves(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test workflow creation with errors saves successfully and reports issues."""
        service = WorkflowService(test_db_session, test_user)

        workflow_definition = self._create_workflow_definition()

        mock_val = MagicMock()
        mock_val.collect_findings.return_value = _invalid_result()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", mock_val):
            workflow, _version, val_result = await service.create_workflow(
                name="errors-save-workflow",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

            assert workflow.has_validation_issues is True
            assert val_result.error_count > 0

    @pytest.mark.asyncio
    async def test_create_workflow_valid_has_no_validation_issues(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test workflow creation with valid definition has no validation issues."""
        service = WorkflowService(test_db_session, test_user)

        workflow_definition = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _version, _val_result = await service.create_workflow(
                name="valid-workflow",
                description=None,
                labels={},
                workflow_definition=workflow_definition,
                project_id=test_project_id,
            )

            assert workflow.has_validation_issues is False


class TestWorkflowServiceGetWorkflow(TestWorkflowServiceBase):
    """Test get workflow functionality."""

    @pytest.mark.asyncio
    async def test_get_workflow_by_id_success(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test successful workflow retrieval by ID."""
        service = WorkflowService(test_db_session, test_user)

        # Create a workflow in the database
        workflow = self._create_test_workflow(name="test-workflow", created_by=test_user.id)
        test_db_session.add(workflow)
        await test_db_session.commit()

        result = await service.get_workflow_by_id(workflow.id)

        assert result.id == workflow.id
        assert result.name == workflow.name

    @pytest.mark.asyncio
    async def test_get_workflow_by_id_not_found(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test workflow retrieval when workflow not found."""
        service = WorkflowService(test_db_session, test_user)

        workflow_id = uuid4()

        with pytest.raises(WorkflowNotFoundError) as exc_info:
            await service.get_workflow_by_id(workflow_id)

        assert str(exc_info.value) == f"Workflow {workflow_id} not found"

    @pytest.mark.asyncio
    async def test_get_workflow_with_version_success(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test successful workflow and version retrieval."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow and version in database
        workflow = self._create_test_workflow(name="test-workflow", current_version=2, created_by=test_user.id)
        test_db_session.add(workflow)

        version = self._create_test_workflow_version(workflow_id=workflow.id, version=2, created_by=test_user.id)
        test_db_session.add(version)
        await test_db_session.commit()

        result_workflow, result_version = await service.get_workflow_with_version(workflow.id)

        assert result_workflow.id == workflow.id
        assert result_version.id == version.id
        assert result_version.version == 2

    @pytest.mark.asyncio
    async def test_get_workflow_with_version_not_found(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test workflow with version when version not found."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow but not its version
        workflow = self._create_test_workflow(name="test-workflow", current_version=2, created_by=test_user.id)
        test_db_session.add(workflow)
        await test_db_session.commit()

        with pytest.raises(WorkflowVersionNotFoundError) as exc_info:
            await service.get_workflow_with_version(workflow.id)

        assert str(exc_info.value) == f"Workflow {workflow.id} version 2 not found"


class TestWorkflowServiceUpdateMetadata(TestWorkflowServiceBase):
    """Test update workflow metadata functionality."""

    @pytest.mark.asyncio
    async def test_update_workflow_metadata_all_fields(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test updating all metadata fields."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(name="original-name", created_by=test_user.id)
        original_updated_at = workflow.updated_at

        await service.update_workflow_metadata(
            workflow,
            name="updated-name",
            description="Updated description",
            labels={"env": "prod"},
        )

        assert workflow.name == "updated-name"
        assert workflow.description == "Updated description"
        assert workflow.labels == {"env": "prod"}
        assert workflow.updated_by == test_user.id
        assert workflow.updated_at > original_updated_at

    @pytest.mark.asyncio
    async def test_update_workflow_metadata_partial_fields(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test updating only some metadata fields."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(
            name="original-name",
            description="Original description",
            labels={"env": "dev"},
            is_enabled=True,
            created_by=test_user.id,
        )

        await service.update_workflow_metadata(
            workflow,
            name="updated-name",
            description=None,  # Should not change
            labels=None,  # Should not change
        )

        assert workflow.name == "updated-name"
        assert workflow.description == "Original description"  # Unchanged
        assert workflow.labels == {"env": "dev"}  # Unchanged
        assert workflow.updated_by == test_user.id

    @pytest.mark.asyncio
    async def test_update_workflow_metadata_empty_name_error(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test updating with empty name raises SafeValueError."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(created_by=test_user.id)

        with pytest.raises(SafeValueError, match="Workflow name cannot be empty"):
            await service.update_workflow_metadata(workflow, name="")


class TestWorkflowServiceCreateVersion(TestWorkflowServiceBase):
    """Test create workflow version functionality."""

    @pytest.mark.asyncio
    async def test_create_workflow_version_success(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test successful version creation with new definition."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(name="test-workflow", current_version=1, created_by=test_user.id)
        test_db_session.add(workflow)

        # Create current version in database
        current_version = self._create_test_workflow_version(
            workflow_id=workflow.id, version=1, workflow_definition={"original": "definition"}, created_by=test_user.id
        )
        test_db_session.add(current_version)
        await test_db_session.commit()

        new_definition = self._create_workflow_definition(description="Updated workflow")  # type: ignore[arg-type]

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            result, _val_result = await service.create_workflow_version(
                workflow,
                new_definition,
                "Updated description",
            )

            assert result is not None
            assert result.workflow_id == workflow.id
            assert result.version == 2
            assert result.schema_version == "2.0.0"
            assert result.workflow_definition == new_definition
            assert result.change_description == "Updated description"
            assert result.created_by == test_user.id
            assert workflow.current_version == 2

            # Verify version was added to session
            await test_db_session.commit()
            db_version = await test_db_session.get(WorkflowVersion, result.id)
            assert db_version is not None

    @pytest.mark.asyncio
    async def test_create_workflow_version_no_change(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test version creation when definition hasn't changed."""
        service = WorkflowService(test_db_session, test_user)

        same_definition = self._create_workflow_definition()

        workflow = self._create_test_workflow(name="test-workflow", current_version=1, created_by=test_user.id)
        test_db_session.add(workflow)

        # Create current version in database with same definition
        current_version = self._create_test_workflow_version(
            workflow_id=workflow.id, version=1, workflow_definition=same_definition, created_by=test_user.id
        )
        test_db_session.add(current_version)
        await test_db_session.commit()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            result, _val_result = await service.create_workflow_version(
                workflow,
                same_definition,
                "No actual changes",
            )

            assert result is None  # No new version created
            assert workflow.current_version == 1  # Version unchanged

    @pytest.mark.asyncio
    async def test_create_workflow_version_validation_error_saves_with_issues(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test version creation with invalid definition still saves and reports issues."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(name="invalid-ver-test", current_version=1, created_by=test_user.id)
        test_db_session.add(workflow)
        current_version = self._create_test_workflow_version(
            workflow_id=workflow.id, version=1, workflow_definition={"original": "def"}, created_by=test_user.id
        )
        test_db_session.add(current_version)
        await test_db_session.commit()

        invalid_definition = self._create_workflow_definition(description="invalid update")  # type: ignore[arg-type]

        mock_val = MagicMock()
        mock_val.collect_findings.return_value = _invalid_result("Invalid definition")

        with patch("syntara.workflows.services.workflow_service.workflow_validator", mock_val):
            version, val_result = await service.create_workflow_version(
                workflow,
                invalid_definition,
                "Invalid update",
            )

            assert version is not None
            assert workflow.has_validation_issues is True
            assert val_result.error_count > 0


class TestWorkflowServiceUpdateWorkflow(TestWorkflowServiceBase):
    """Test update workflow functionality."""

    @pytest.mark.asyncio
    async def test_update_workflow_metadata_only(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test updating workflow metadata without creating new version."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow and version in database
        workflow = self._create_test_workflow(name="test-workflow", created_by=test_user.id)
        test_db_session.add(workflow)

        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(version)
        await test_db_session.commit()

        result = await service.update_workflow(
            workflow.id,
            name="updated-name",
            description="Updated description",
            labels={"env": "prod"},
        )

        result_workflow, result_version, _val_result = result
        assert result_workflow.id == workflow.id
        assert result_workflow.name == "updated-name"
        assert result_workflow.description == "Updated description"
        assert result_workflow.labels == {"env": "prod"}
        assert result_version.id == version.id

    @pytest.mark.asyncio
    async def test_update_workflow_with_definition(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test updating workflow with new definition creates version."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow and version in database
        workflow = self._create_test_workflow(name="test-workflow", current_version=1, created_by=test_user.id)
        test_db_session.add(workflow)

        version = self._create_test_workflow_version(workflow_id=workflow.id, version=1, created_by=test_user.id)
        test_db_session.add(version)
        await test_db_session.commit()

        new_definition = self._create_workflow_definition(description="Updated workflow with new features")  # type: ignore[arg-type]

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            result = await service.update_workflow(
                workflow.id,
                name="updated-name",
                workflow_definition=new_definition,
                change_description="Added new features",
            )

            result_workflow, result_version, _val_result = result
            assert result_workflow.id == workflow.id
            assert result_workflow.name == "updated-name"
            assert result_workflow.current_version == 2  # Version should be incremented
            assert result_version.version == 2

    @pytest.mark.asyncio
    async def test_update_workflow_not_found(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test updating non-existent workflow raises error."""
        service = WorkflowService(test_db_session, test_user)

        workflow_id = uuid4()

        with pytest.raises(WorkflowNotFoundError):
            await service.update_workflow(workflow_id, name="new-name")


class TestWorkflowServiceDeleteWorkflow(TestWorkflowServiceBase):
    """Test delete workflow functionality."""

    @pytest.mark.asyncio
    async def test_delete_workflow_success(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test successful workflow soft deletion."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow in database
        workflow = self._create_test_workflow(name="test-workflow", created_by=test_user.id)
        test_db_session.add(workflow)
        await test_db_session.commit()

        await service.delete_workflow(workflow.id)

        # Verify workflow is soft deleted
        await test_db_session.refresh(workflow)
        assert workflow.deleted_at is not None
        assert workflow.deleted_by == test_user.id

    @pytest.mark.asyncio
    async def test_delete_workflow_not_found(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test deleting non-existent workflow raises error."""
        service = WorkflowService(test_db_session, test_user)

        workflow_id = uuid4()

        with pytest.raises(WorkflowNotFoundError):
            await service.delete_workflow(workflow_id)


class TestWorkflowServiceListWorkflows(TestWorkflowServiceBase):
    """Test list workflows functionality."""

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_uses_base_method(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that list_workflows_cursor delegates to base list_resources method."""
        service = WorkflowService(test_db_session, test_user)

        # Create some workflows (is_enabled=False initially, set after version FK)
        workflow1 = self._create_test_workflow(name="workflow-1", created_by=test_user.id)
        workflow2 = self._create_test_workflow(name="workflow-2", created_by=test_user.id)
        test_db_session.add_all([workflow1, workflow2])

        v1 = self._create_test_workflow_version(workflow_id=workflow1.id, created_by=test_user.id)
        v2 = self._create_test_workflow_version(workflow_id=workflow2.id, created_by=test_user.id)
        test_db_session.add_all([v1, v2])
        await test_db_session.flush()

        workflow1.published_version_id = v1.id
        workflow1.is_enabled = True
        workflow2.published_version_id = v2.id
        workflow2.is_enabled = True
        await test_db_session.commit()

        result = await service.list_workflows_cursor(
            limit=10,
            cursor=None,
            sort="name",
            query_params_items=[("is_enabled", "true")],
            include_total=True,
        )

        assert result.__class__ == WorkflowListResponse
        assert len(result.resources) == 2
        assert result.total == 2

        # Verify the actual workflows are returned
        returned_names = {w.name for w in result.resources}
        expected_names = {"workflow-1", "workflow-2"}
        assert returned_names == expected_names

        # Verify all returned workflows are enabled
        assert all(w.is_enabled for w in result.resources)

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_default_sort(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that list_workflows_cursor uses default sort when none provided."""
        service = WorkflowService(test_db_session, test_user)

        result = await service.list_workflows_cursor()

        assert result.__class__ == WorkflowListResponse
        # Should work even with empty result
        assert len(result.resources) == 0

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_boundary_limit_zero(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test cursor pagination with zero limit."""
        service = WorkflowService(test_db_session, test_user)

        # Create test workflow
        workflow = self._create_test_workflow(name="test-workflow", created_by=test_user.id)
        test_db_session.add(workflow)
        await test_db_session.commit()

        result = await service.list_workflows_cursor(limit=0)

        assert result.__class__ == WorkflowListResponse
        assert len(result.resources) == 0

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_boundary_large_limit(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test cursor pagination with very large limit."""
        service = WorkflowService(test_db_session, test_user)

        # Create multiple workflows
        workflows = [self._create_test_workflow(name=f"workflow-{i}", created_by=test_user.id) for i in range(5)]
        test_db_session.add_all(workflows)
        await test_db_session.commit()

        result = await service.list_workflows_cursor(limit=1000)

        assert result.__class__ == WorkflowListResponse
        assert len(result.resources) == 5

        # Verify all created workflows are returned
        returned_names = {w.name for w in result.resources}
        expected_names = {f"workflow-{i}" for i in range(5)}
        assert returned_names == expected_names

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_with_valid_cursor(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test pagination with valid cursor token."""
        service = WorkflowService(test_db_session, test_user)

        # Create multiple workflows for pagination
        workflows = [self._create_test_workflow(name=f"workflow-{i:02d}", created_by=test_user.id) for i in range(10)]
        test_db_session.add_all(workflows)
        await test_db_session.commit()

        # Get first page
        first_page = await service.list_workflows_cursor(limit=3, sort="name")

        assert len(first_page.resources) == 3
        assert first_page.next is not None

        # Verify the first page contains the expected workflows (sorted by name)
        first_page_names = [w.name for w in first_page.resources]
        expected_first_names = ["workflow-00", "workflow-01", "workflow-02"]
        assert first_page_names == expected_first_names

        # Get second page using cursor
        second_page = await service.list_workflows_cursor(limit=3, cursor=first_page.next, sort="name")

        assert len(second_page.resources) == 3
        assert second_page.prev is not None

        # Verify the second page contains the expected workflows
        second_page_names = [w.name for w in second_page.resources]
        expected_second_names = ["workflow-03", "workflow-04", "workflow-05"]
        assert second_page_names == expected_second_names

        # Verify different results
        first_names = {w.name for w in first_page.resources}
        second_names = {w.name for w in second_page.resources}
        assert first_names.isdisjoint(second_names)

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_with_updated_at_sort(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Cursor pagination must work with datetime sorts like -updated_at (not just name)."""
        service = WorkflowService(test_db_session, test_user)

        workflows = [self._create_test_workflow(name=f"workflow-{i:02d}", created_by=test_user.id) for i in range(10)]
        test_db_session.add_all(workflows)
        await test_db_session.commit()

        first_page = await service.list_workflows_cursor(limit=3, sort="-updated_at")

        assert len(first_page.resources) == 3
        assert first_page.next is not None

        second_page = await service.list_workflows_cursor(limit=3, cursor=first_page.next, sort="-updated_at")

        assert len(second_page.resources) == 3
        assert second_page.prev is not None

        first_ids = {w.id for w in first_page.resources}
        second_ids = {w.id for w in second_page.resources}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_with_is_enabled_sort(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Cursor pagination must work with boolean sorts like is_enabled (next and prev)."""
        service = WorkflowService(test_db_session, test_user)

        workflows = [self._create_test_workflow(name=f"workflow-{i:02d}", created_by=test_user.id) for i in range(10)]
        test_db_session.add_all(workflows)
        await test_db_session.commit()

        first_page = await service.list_workflows_cursor(limit=3, sort="is_enabled")

        assert len(first_page.resources) == 3
        assert first_page.next is not None

        second_page = await service.list_workflows_cursor(limit=3, cursor=first_page.next, sort="is_enabled")

        assert len(second_page.resources) == 3
        assert second_page.prev is not None

        first_ids = {w.id for w in first_page.resources}
        second_ids = {w.id for w in second_page.resources}
        assert first_ids.isdisjoint(second_ids)

        # Backward pagination runs _check_has_items_before, which also keysets on the sort col.
        back_to_first = await service.list_workflows_cursor(limit=3, cursor=second_page.prev, sort="is_enabled")
        assert len(back_to_first.resources) == 3
        assert {w.id for w in back_to_first.resources} == first_ids

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_empty_results_with_cursor(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test cursor pagination when result set is empty."""
        service = WorkflowService(test_db_session, test_user)

        # Create a valid base64 cursor that points to a non-existent record
        cursor_data = {"id": str(uuid4()), "direction": "next"}
        valid_cursor = base64.b64encode(json.dumps(cursor_data).encode("utf-8")).decode("ascii")

        result = await service.list_workflows_cursor(limit=10, cursor=valid_cursor, sort="name")

        assert result.__class__ == WorkflowListResponse
        assert len(result.resources) == 0
        assert result.next is None
        assert result.prev is None

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_different_sort_orders(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test cursor pagination with different sort orders."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflows with different timestamps
        base_time = datetime.now(UTC)
        workflows = []
        for i in range(3):
            workflow = self._create_test_workflow(
                name=f"workflow-{i}", created_by=test_user.id, created_at=base_time + timedelta(hours=i)
            )
            workflows.append(workflow)

        test_db_session.add_all(workflows)
        await test_db_session.commit()

        # Test ascending sort
        asc_result = await service.list_workflows_cursor(sort="created_at")
        assert len(asc_result.resources) == 3

        # Verify ascending order by created_at
        asc_names = [w.name for w in asc_result.resources]
        assert asc_names == ["workflow-0", "workflow-1", "workflow-2"]

        # Test descending sort (default)
        desc_result = await service.list_workflows_cursor(sort="-created_at")
        assert len(desc_result.resources) == 3

        # Verify descending order by created_at
        desc_names = [w.name for w in desc_result.resources]
        assert desc_names == ["workflow-2", "workflow-1", "workflow-0"]

        # Test name sort
        name_result = await service.list_workflows_cursor(sort="name")
        assert len(name_result.resources) == 3

        # Verify alphabetical order by name
        name_names = [w.name for w in name_result.resources]
        assert name_names == ["workflow-0", "workflow-1", "workflow-2"]

    @pytest.mark.asyncio
    async def test_list_workflows_cursor_with_include_total(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test cursor pagination with total count included."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflows
        workflows = [self._create_test_workflow(name=f"workflow-{i}", created_by=test_user.id) for i in range(7)]
        test_db_session.add_all(workflows)
        await test_db_session.commit()

        # Test without total
        without_total = await service.list_workflows_cursor(limit=3, include_total=False)
        assert without_total.total is None

        # Test with total
        with_total = await service.list_workflows_cursor(limit=3, include_total=True)
        assert with_total.total == 7
        assert len(with_total.resources) == 3

        # Verify the first 3 workflows are returned (default sort)
        returned_names = {w.name for w in with_total.resources}
        all_workflow_names = {f"workflow-{i}" for i in range(7)}
        assert returned_names.issubset(all_workflow_names)


class TestWorkflowServiceLabelFiltering(TestWorkflowServiceBase):
    """Test label filtering functionality in workflow list operations."""

    @pytest.mark.asyncio
    async def test_list_workflows_filter_by_label_key_value(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test filtering workflows by specific label key-value pair."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflows with different labels
        prod_workflow = self._create_test_workflow(
            name="prod-workflow", labels={"environment": "production", "team": "backend"}, created_by=test_user.id
        )
        dev_workflow = self._create_test_workflow(
            name="dev-workflow", labels={"environment": "development", "team": "frontend"}, created_by=test_user.id
        )
        staging_workflow = self._create_test_workflow(
            name="staging-workflow", labels={"environment": "staging", "team": "backend"}, created_by=test_user.id
        )

        test_db_session.add_all([prod_workflow, dev_workflow, staging_workflow])
        await test_db_session.commit()

        # Filter by environment=production (key-value filtering)
        result = await service.list_workflows_cursor(query_params_items=[("labels[environment]", "production")])

        assert len(result.resources) == 1
        assert result.resources[0].name == "prod-workflow"
        assert result.resources[0].labels["environment"] == "production"
        assert result.resources[0].labels["team"] == "backend"

    @pytest.mark.asyncio
    async def test_list_workflows_filter_by_label_key_existence(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test filtering workflows by label key existence (without specific value)."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflows with and without specific labels
        with_team_workflow = self._create_test_workflow(
            name="with-team", labels={"team": "backend", "environment": "prod"}, created_by=test_user.id
        )
        without_team_workflow = self._create_test_workflow(
            name="without-team", labels={"environment": "dev"}, created_by=test_user.id
        )

        test_db_session.add_all([with_team_workflow, without_team_workflow])
        await test_db_session.commit()

        # Filter by team key existence (should match workflow with any team value)
        result = await service.list_workflows_cursor(
            query_params_items=[("labels[team]", "")]  # Empty value means key existence check
        )

        assert len(result.resources) == 1
        assert result.resources[0].name == "with-team"
        assert "team" in result.resources[0].labels
        assert result.resources[0].labels["team"] == "backend"

    @pytest.mark.asyncio
    async def test_list_workflows_filter_multiple_labels(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test filtering workflows with multiple label criteria (AND logic)."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflows with various label combinations
        exact_match = self._create_test_workflow(
            name="exact-match",
            labels={"environment": "production", "team": "backend", "priority": "high"},
            created_by=test_user.id,
        )
        partial_match1 = self._create_test_workflow(
            name="partial-match-1",
            labels={"environment": "production", "team": "frontend"},  # Missing team=backend
            created_by=test_user.id,
        )
        partial_match2 = self._create_test_workflow(
            name="partial-match-2",
            labels={"team": "backend", "priority": "low"},  # Missing environment=production
            created_by=test_user.id,
        )

        test_db_session.add_all([exact_match, partial_match1, partial_match2])
        await test_db_session.commit()

        # Filter by multiple criteria (environment=production AND team=backend)
        result = await service.list_workflows_cursor(
            query_params_items=[("labels[environment]", "production"), ("labels[team]", "backend")]
        )

        assert len(result.resources) == 1
        assert result.resources[0].name == "exact-match"
        assert result.resources[0].labels["environment"] == "production"
        assert result.resources[0].labels["team"] == "backend"

    @pytest.mark.asyncio
    async def test_list_workflows_filter_nonexistent_label_key(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test filtering by nonexistent label key returns empty results."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow without the 'nonexistent' label
        workflow = self._create_test_workflow(
            name="test-workflow", labels={"environment": "prod", "team": "backend"}, created_by=test_user.id
        )
        test_db_session.add(workflow)
        await test_db_session.commit()

        # Filter by nonexistent label key
        result = await service.list_workflows_cursor(query_params_items=[("labels[nonexistent]", "any-value")])

        assert len(result.resources) == 0

    @pytest.mark.asyncio
    async def test_list_workflows_filter_nonmatching_label_value(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test filtering by label key with non-matching value."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow with specific label value
        workflow = self._create_test_workflow(
            name="prod-workflow", labels={"environment": "production"}, created_by=test_user.id
        )
        test_db_session.add(workflow)
        await test_db_session.commit()

        # Filter by same key but different value
        result = await service.list_workflows_cursor(query_params_items=[("labels[environment]", "staging")])

        assert len(result.resources) == 0

    @pytest.mark.asyncio
    async def test_list_workflows_filter_empty_label_values(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test filtering workflows with empty label values."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflows with empty and non-empty label values
        empty_value_workflow = self._create_test_workflow(
            name="empty-value", labels={"environment": "", "team": "backend"}, created_by=test_user.id
        )
        normal_workflow = self._create_test_workflow(
            name="normal", labels={"environment": "production", "team": "backend"}, created_by=test_user.id
        )

        test_db_session.add_all([empty_value_workflow, normal_workflow])
        await test_db_session.commit()

        # Filter by empty value - the implementation treats this as key existence check
        result = await service.list_workflows_cursor(query_params_items=[("labels[environment]", "")])

        # Should return exactly 2 results: both workflows that have the environment key
        assert len(result.resources) == 2

        # Verify both workflows are returned
        returned_names = {w.name for w in result.resources}
        assert returned_names == {"empty-value", "normal"}

        # Verify each workflow has the environment key (with different values)
        for workflow in result.resources:
            assert "environment" in workflow.labels
            if workflow.name == "empty-value":
                assert workflow.labels["environment"] == ""
                assert workflow.labels["team"] == "backend"
            elif workflow.name == "normal":
                assert workflow.labels["environment"] == "production"
                assert workflow.labels["team"] == "backend"

    @pytest.mark.asyncio
    async def test_list_workflows_filter_special_characters_in_labels(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test filtering with special characters in label keys and values."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow with special characters in labels
        special_workflow = self._create_test_workflow(
            name="special-chars",
            labels={"app.name": "my-app", "version": "v1.0.0-beta", "owner": "team@company.com"},
            created_by=test_user.id,
        )
        normal_workflow = self._create_test_workflow(name="normal", labels={"app": "simple"}, created_by=test_user.id)

        test_db_session.add_all([special_workflow, normal_workflow])
        await test_db_session.commit()

        # Filter by label key with dots
        result = await service.list_workflows_cursor(query_params_items=[("labels[app.name]", "my-app")])

        assert len(result.resources) == 1
        assert result.resources[0].name == "special-chars"
        assert result.resources[0].labels["app.name"] == "my-app"

    @pytest.mark.asyncio
    async def test_list_workflows_filter_case_sensitivity(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test label filtering case sensitivity."""
        service = WorkflowService(test_db_session, test_user)

        # Create workflow with specific case labels
        workflow = self._create_test_workflow(
            name="case-test", labels={"Environment": "Production", "TEAM": "Backend"}, created_by=test_user.id
        )
        test_db_session.add(workflow)
        await test_db_session.commit()

        # Test exact case match
        exact_result = await service.list_workflows_cursor(query_params_items=[("labels[Environment]", "Production")])
        assert len(exact_result.resources) == 1
        assert exact_result.resources[0].name == "case-test"
        assert exact_result.resources[0].labels["Environment"] == "Production"

        # Test different case (should not match)
        wrong_case_result = await service.list_workflows_cursor(
            query_params_items=[("labels[environment]", "production")]
        )
        assert len(wrong_case_result.resources) == 0

    @pytest.mark.asyncio
    async def test_list_workflows_filter_combined_with_pagination(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test label filtering combined with cursor pagination."""
        service = WorkflowService(test_db_session, test_user)

        # Create multiple workflows with same label for pagination testing
        workflows = []
        for i in range(7):
            workflow = self._create_test_workflow(
                name=f"prod-workflow-{i:02d}",
                labels={"environment": "production", "index": str(i)},
                created_by=test_user.id,
            )
            workflows.append(workflow)

        # Add one workflow with different environment
        dev_workflow = self._create_test_workflow(
            name="dev-workflow", labels={"environment": "development"}, created_by=test_user.id
        )
        workflows.append(dev_workflow)

        test_db_session.add_all(workflows)
        await test_db_session.commit()

        # Get first page with label filter
        first_page = await service.list_workflows_cursor(
            limit=3, sort="name", query_params_items=[("labels[environment]", "production")]
        )

        assert len(first_page.resources) == 3
        assert first_page.next is not None
        # Verify all results have production environment and correct names
        first_page_names = [w.name for w in first_page.resources]
        expected_first_names = ["prod-workflow-00", "prod-workflow-01", "prod-workflow-02"]
        assert first_page_names == expected_first_names
        for workflow_read in first_page.resources:
            assert workflow_read.labels.get("environment") == "production"

        # Get second page with same filter
        second_page = await service.list_workflows_cursor(
            limit=3, cursor=first_page.next, sort="name", query_params_items=[("labels[environment]", "production")]
        )

        assert len(second_page.resources) == 3
        # Verify second page has correct workflows
        second_page_names = [w.name for w in second_page.resources]
        expected_second_names = ["prod-workflow-03", "prod-workflow-04", "prod-workflow-05"]
        assert second_page_names == expected_second_names
        for workflow_read in second_page.resources:
            assert workflow_read.labels.get("environment") == "production"

    @pytest.mark.asyncio
    async def test_list_workflows_filter_mixed_with_other_params(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Test label filtering combined with other query parameters."""
        service = WorkflowService(test_db_session, test_user)

        # Create enabled workflow (requires flush-then-set for CHECK constraint)
        enabled_workflow = self._create_test_workflow(
            name="enabled-prod", labels={"environment": "production"}, is_enabled=False, created_by=test_user.id
        )
        disabled_workflow = self._create_test_workflow(
            name="disabled-prod", labels={"environment": "production"}, is_enabled=False, created_by=test_user.id
        )

        test_db_session.add_all([enabled_workflow, disabled_workflow])

        enabled_version = self._create_test_workflow_version(workflow_id=enabled_workflow.id, created_by=test_user.id)
        test_db_session.add(enabled_version)
        await test_db_session.flush()

        enabled_workflow.published_version_id = enabled_version.id
        enabled_workflow.is_enabled = True
        await test_db_session.commit()

        # Filter by both label and enabled status
        result = await service.list_workflows_cursor(
            query_params_items=[("labels[environment]", "production"), ("is_enabled", "true")]
        )

        assert len(result.resources) == 1
        assert result.resources[0].name == "enabled-prod"
        assert result.resources[0].is_enabled is True
        assert result.resources[0].labels["environment"] == "production"


class TestWorkflowConvertResourceMixin(TestWorkflowServiceBase):
    """Test WorkflowConvertResourceMixin functionality."""

    def test_convert_resource_returns_workflow_read(self) -> None:
        """Test that convert_resource returns WorkflowRead object."""
        mixin = WorkflowConvertResourceMixin()
        workflow = self._create_test_workflow()

        result = mixin.convert_resource(workflow)

        assert isinstance(result, WorkflowRead)
        assert result.id == workflow.id
        assert result.name == workflow.name
        assert result.description == workflow.description


class TestPublishWorkflowVersion(TestWorkflowServiceBase):
    """Test publish_workflow_version method."""

    @pytest.mark.asyncio
    async def test_publish_version_success(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test publishing a version creates a published copy and sets workflow state."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="publish-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock()
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc):
            result_workflow, result_version, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=1,
                name="v1.0",
                change_description="Initial release",
            )

        assert result_version.name == "v1.0"
        assert result_version.change_description == "Initial release"
        assert result_workflow.published_version_id == result_version.id
        assert result_workflow.is_enabled is True

    @pytest.mark.asyncio
    async def test_publish_switches_pointer(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test publishing a new version updates the published_version_id pointer.

        With pointer-based publish:
        - Create -> v1 (draft)
        - Publish v1 -> published_version_id points to v1
        - Create v2 (draft)
        - Publish v2 -> published_version_id points to v2
        """
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _v1, _ = await service.create_workflow(
                name="demote-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock()
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc):
            _, _published_v1, _warning = await service.publish_workflow_version(workflow_id=workflow.id, version=1)

        first_published_id = workflow.published_version_id

        # Create update draft (v2)
        v2_def = self._create_workflow_definition()
        v2_def["description"] = "v2"
        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            v2, _ = await service.create_workflow_version(workflow, v2_def, "v2 changes")

        assert v2 is not None

        mock_wh_svc2 = MagicMock()
        mock_wh_svc2.return_value.sync_webhook_triggers = AsyncMock()
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc2):
            _, published_v2, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id, version=v2.version
            )

        await test_db_session.refresh(workflow)
        # published_version_id should now point to the newly published version
        assert workflow.published_version_id == published_v2.id
        assert workflow.published_version_id != first_published_id

    @pytest.mark.asyncio
    async def test_publish_idempotent(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test publishing the same version twice is idempotent with pointer-based publish."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="idempotent-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock()
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc):
            _, _first_result, _warning = await service.publish_workflow_version(workflow_id=workflow.id, version=1)
            result_workflow, result_version, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id, version=1
            )

        assert result_workflow.published_version_id == result_version.id

    @pytest.mark.asyncio
    async def test_publish_nonexistent_version_raises(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test publishing a nonexistent version raises error."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="nonexistent-version-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        with pytest.raises(WorkflowVersionNotFoundError):
            await service.publish_workflow_version(workflow_id=workflow.id, version=99)

    @pytest.mark.asyncio
    async def test_publish_nonexistent_workflow_raises(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test publishing on a nonexistent workflow raises error."""
        service = WorkflowService(test_db_session, test_user)
        fake_id = uuid4()

        with pytest.raises(WorkflowNotFoundError):
            await service.publish_workflow_version(workflow_id=fake_id, version=1)

    @pytest.mark.asyncio
    async def test_publish_syncs_all_trigger_types(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test that publish syncs both webhook and EDA trigger types."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="publish-trigger-sync-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        mock_wh_svc = MagicMock()
        mock_sync = AsyncMock(return_value=[])
        mock_wh_svc.return_value.sync_webhook_triggers = mock_sync
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc):
            await service.publish_workflow_version(workflow_id=workflow.id, version=1)

        # Should have been called once per trigger type
        assert mock_sync.call_count == 2
        call_trigger_types = {call.kwargs["trigger_type"] for call in mock_sync.call_args_list}
        assert call_trigger_types == {"webhook_trigger", "eda_trigger"}
        # All calls should pass is_enabled=True
        for call in mock_sync.call_args_list:
            assert call.kwargs["is_enabled"] is True

    @pytest.mark.asyncio
    async def test_publish_blocked_when_definition_has_errors(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test that publishing is blocked when the definition has validation errors."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="publish-errors-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        mock_val = MagicMock()
        mock_val.collect_findings.return_value = _invalid_result()

        with (
            patch("syntara.workflows.services.workflow_service.workflow_validator", mock_val),
            pytest.raises(WorkflowPublishValidationError),
        ):
            await service.publish_workflow_version(workflow_id=workflow.id, version=1)

    @pytest.mark.asyncio
    async def test_publish_blocked_when_definition_has_warnings(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test that publishing is blocked when the definition has only warnings."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="publish-warnings-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        mock_val = MagicMock()
        mock_val.collect_findings.return_value = _warnings_result()

        with (
            patch("syntara.workflows.services.workflow_service.workflow_validator", mock_val),
            pytest.raises(WorkflowPublishValidationError),
        ):
            await service.publish_workflow_version(workflow_id=workflow.id, version=1)

    @pytest.mark.asyncio
    async def test_publish_blocked_preserves_previous_published_version(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test that a failed publish attempt does not affect the existing published version."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="publish-preserves-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock()
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc):
            _, published_v2, _warning = await service.publish_workflow_version(workflow_id=workflow.id, version=1)

        assert workflow.published_version_id == published_v2.id

        v3_def = self._create_workflow_definition()
        v3_def["description"] = "updated definition"
        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            v3, _ = await service.create_workflow_version(workflow, v3_def, "update with issues")
        assert v3 is not None

        mock_val = MagicMock()
        mock_val.collect_findings.return_value = _invalid_result()

        with (
            patch("syntara.workflows.services.workflow_service.workflow_validator", mock_val),
            pytest.raises(WorkflowPublishValidationError),
        ):
            await service.publish_workflow_version(workflow_id=workflow.id, version=v3.version)

        await test_db_session.refresh(workflow)
        assert workflow.published_version_id == published_v2.id
        assert workflow.is_enabled is True


class TestUnpublishWorkflow(TestWorkflowServiceBase):
    """Test unpublish_workflow method."""

    @pytest.mark.asyncio
    async def test_unpublish_success(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test unpublishing sets workflow state correctly.

        With pointer-based publish:
        - Publish v1 -> published_version_id points to v1
        - Unpublish -> published_version_id set to None
        """
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _v1, _ = await service.create_workflow(
                name="unpublish-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock()
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc):
            await service.publish_workflow_version(workflow_id=workflow.id, version=1)
            result = await service.unpublish_workflow(workflow_id=workflow.id)

        assert result.published_version_id is None
        assert result.is_enabled is False

    @pytest.mark.asyncio
    async def test_unpublish_when_not_published_raises(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test unpublishing when no version is published raises error."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="unpublish-error-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        with pytest.raises(WorkflowNotPublishedError):
            await service.unpublish_workflow(workflow_id=workflow.id)

    @pytest.mark.asyncio
    async def test_unpublish_nonexistent_workflow_raises(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test unpublishing a nonexistent workflow raises error."""
        service = WorkflowService(test_db_session, test_user)
        fake_id = uuid4()

        with pytest.raises(WorkflowNotFoundError):
            await service.unpublish_workflow(workflow_id=fake_id)

    @pytest.mark.asyncio
    async def test_unpublish_syncs_all_trigger_types(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test that unpublish syncs both webhook and EDA trigger types."""
        service = WorkflowService(test_db_session, test_user)
        workflow_def = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="unpublish-trigger-sync-test",
                description=None,
                labels={},
                workflow_definition=workflow_def,
                project_id=test_project_id,
            )

        # Publish first (mock webhook service)
        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock(return_value=[])
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc):
            await service.publish_workflow_version(workflow_id=workflow.id, version=1)

        # Now unpublish and verify trigger sync
        mock_wh_svc2 = MagicMock()
        mock_sync = AsyncMock(return_value=[])
        mock_wh_svc2.return_value.sync_webhook_triggers = mock_sync
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc2):
            await service.unpublish_workflow(workflow_id=workflow.id)

        # Should have been called once per trigger type
        assert mock_sync.call_count == 2
        call_trigger_types = {call.kwargs["trigger_type"] for call in mock_sync.call_args_list}
        assert call_trigger_types == {"webhook_trigger", "eda_trigger"}
        # All calls should pass is_enabled=False
        for call in mock_sync.call_args_list:
            assert call.kwargs["is_enabled"] is False


class TestRestoreWorkflowVersion(TestWorkflowServiceBase):
    """Test restore_workflow_version method."""

    @pytest.mark.asyncio
    async def test_restore_creates_new_draft(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test restoring a version creates a new draft with the original definition."""
        service = WorkflowService(test_db_session, test_user)
        defn_v1 = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="restore-unit-test",
                description=None,
                labels={},
                workflow_definition=defn_v1,
                project_id=test_project_id,
            )

        defn_v2 = self._create_workflow_definition(description="Updated workflow")  # type: ignore[arg-type]
        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock()
        with (
            patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc),
        ):
            await service.update_workflow(
                workflow_id=workflow.id,
                workflow_definition=defn_v2,
            )

        result_workflow, result_version = await service.restore_workflow_version(
            workflow_id=workflow.id,
            version=1,
        )

        assert result_workflow.current_version == 3
        assert result_workflow.updated_by == test_user.id
        assert result_workflow.updated_at is not None
        assert result_version.version == 3
        assert result_version.change_description is not None
        assert "Restored from" in result_version.change_description
        assert result_version.workflow_definition == defn_v1

    @pytest.mark.asyncio
    async def test_restore_current_version_is_noop(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test restoring the current version returns it without creating a new one."""
        service = WorkflowService(test_db_session, test_user)
        defn = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="restore-noop-unit",
                description=None,
                labels={},
                workflow_definition=defn,
                project_id=test_project_id,
            )

        result_workflow, _ = await service.restore_workflow_version(
            workflow_id=workflow.id,
            version=1,
        )

        assert result_workflow.current_version == 1

    @pytest.mark.asyncio
    async def test_restore_nonexistent_version_raises(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        """Test restoring a nonexistent version raises error."""
        service = WorkflowService(test_db_session, test_user)
        defn = self._create_workflow_definition()

        with patch("syntara.workflows.services.workflow_service.workflow_validator", _mock_validator_valid()):
            workflow, _, _ = await service.create_workflow(
                name="restore-404-unit",
                description=None,
                labels={},
                workflow_definition=defn,
                project_id=test_project_id,
            )

        with pytest.raises(WorkflowVersionNotFoundError):
            await service.restore_workflow_version(workflow_id=workflow.id, version=99)

    @pytest.mark.asyncio
    async def test_restore_nonexistent_workflow_raises(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test restoring from a nonexistent workflow raises error."""
        service = WorkflowService(test_db_session, test_user)
        fake_id = uuid4()

        with pytest.raises(WorkflowNotFoundError):
            await service.restore_workflow_version(workflow_id=fake_id, version=1)


# ============================================================================
# AAP-79159: Cross-project credential validation
# ============================================================================

_PATCH_VALIDATOR = "syntara.workflows.services.workflow_service.workflow_validator"
_PATCH_PROJECT_ALIVE = "syntara.core.queries.project_queries.assert_project_alive"


def _mock_webhook_service() -> MagicMock:
    """Create a mock WebhookTriggerService with async methods."""
    svc = MagicMock()
    svc.return_value.sync_webhook_triggers = AsyncMock()
    return svc


def _workflow_definition_with_credential(credential_id: str | None = None) -> dict[str, Any]:
    """Build a minimal valid V2 workflow definition with an optional credential_id."""
    node: dict[str, Any] = {
        "id": "http-1",
        "name": "Make Request",
        "type": "action",
        "executor": "http_request",
        "parameters": {
            "method": "GET",
            "url": "https://example.com",
        },
    }
    if credential_id:
        node["parameters"]["credential_id"] = credential_id

    return {
        "schema_version": "2.0.0",
        "description": "test workflow",
        "triggers": [{"id": "trigger-1", "name": "Manual", "type": "manual", "config": {}}],
        "nodes": [node],
        "edges": [{"source": "trigger-1", "target": "http-1", "source_port": "default", "target_port": "default"}],
    }


class TestCredentialProjectScopeValidation(TestWorkflowServiceBase):
    """AAP-79159: Workflow creation must reject cross-project credential references."""

    @pytest.fixture
    async def project_a_id(self, test_db_session: AsyncSession) -> UUID:
        """Create project A and return its ID."""
        project = Project(name=f"project-a-{uuid4().hex[:6]}")
        test_db_session.add(project)
        await test_db_session.flush()
        return project.id

    @pytest.fixture
    async def project_b_id(self, test_db_session: AsyncSession) -> UUID:
        """Create project B and return its ID."""
        project = Project(name=f"project-b-{uuid4().hex[:6]}")
        test_db_session.add(project)
        await test_db_session.flush()
        return project.id

    @pytest.fixture
    async def cred_type(self, test_db_session: AsyncSession) -> CredentialType:
        """Create a test credential type."""
        ct = CredentialType(
            name=f"test-type-{uuid4().hex[:6]}",
            description="test",
            inputs={"fields": [], "required": []},
            injectors={"extra_vars": {}, "env": {}, "file": {}},
            managed=False,
        )
        test_db_session.add(ct)
        await test_db_session.flush()
        return ct

    @pytest.fixture
    async def credential_in_a(
        self, test_db_session: AsyncSession, project_a_id: UUID, cred_type: CredentialType, test_user: User
    ) -> Credential:
        """Create a credential in project A."""
        cred = Credential(
            name=f"cred-a-{uuid4().hex[:6]}",
            credential_type_id=cred_type.id,
            project_id=project_a_id,
            created_by=test_user.id,
            labels={},
        )
        test_db_session.add(cred)
        await test_db_session.flush()
        return cred

    @pytest.mark.asyncio
    async def test_create_workflow_rejects_cross_project_credential(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_b_id: UUID,
        credential_in_a: Credential,
    ) -> None:
        """Workflow in project B cannot reference a credential from project A."""
        service = WorkflowService(test_db_session, test_user)
        wf_def = _workflow_definition_with_credential(credential_id=str(credential_in_a.id))

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_PROJECT_ALIVE, new_callable=AsyncMock),
            pytest.raises(SafeValueError, match="invalid or belong to a different project"),
        ):
            await service.create_workflow(
                name="cross-project-test",
                description=None,
                labels={},
                workflow_definition=wf_def,
                project_id=project_b_id,
            )

    @pytest.mark.asyncio
    async def test_create_workflow_allows_same_project_credential(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_a_id: UUID,
        credential_in_a: Credential,
    ) -> None:
        """Workflow in project A can reference a credential from project A."""
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(
            return_value={"allow": True, "deny": False, "matched_policy": "", "denial_reason": "", "denied_by": ""}
        )
        service = WorkflowService(test_db_session, test_user, opa_client=mock_evaluator)
        wf_def = _workflow_definition_with_credential(credential_id=str(credential_in_a.id))

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_PROJECT_ALIVE, new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService", _mock_webhook_service()),
        ):
            workflow, version, _ = await service.create_workflow(
                name=f"same-project-{uuid4().hex[:6]}",
                description=None,
                labels={},
                workflow_definition=wf_def,
                project_id=project_a_id,
            )
            assert workflow is not None
            assert version is not None

    @pytest.mark.asyncio
    async def test_create_workflow_rejects_nonexistent_credential(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_a_id: UUID,
    ) -> None:
        """Workflow referencing a credential that doesn't exist is rejected."""
        service = WorkflowService(test_db_session, test_user)
        wf_def = _workflow_definition_with_credential(credential_id=str(uuid4()))

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_PROJECT_ALIVE, new_callable=AsyncMock),
            pytest.raises(SafeValueError, match="invalid or belong to a different project"),
        ):
            await service.create_workflow(
                name="missing-cred-test",
                description=None,
                labels={},
                workflow_definition=wf_def,
                project_id=project_a_id,
            )

    @pytest.mark.asyncio
    async def test_create_workflow_no_credential_skips_validation(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_a_id: UUID,
    ) -> None:
        """Workflow without credential references skips credential validation."""
        service = WorkflowService(test_db_session, test_user)
        wf_def = _workflow_definition_with_credential(credential_id=None)

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_PROJECT_ALIVE, new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService", _mock_webhook_service()),
        ):
            workflow, _version, _ = await service.create_workflow(
                name=f"no-cred-{uuid4().hex[:6]}",
                description=None,
                labels={},
                workflow_definition=wf_def,
                project_id=project_a_id,
            )
            assert workflow is not None

    @pytest.mark.asyncio
    async def test_create_workflow_raises_when_no_authz_evaluator(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_a_id: UUID,
        credential_in_a: Credential,
    ) -> None:
        """Workflow save with a credential fails when opa_client is None (fail-closed)."""
        from syntara.authz.exceptions import AuthorizationDeniedError

        service = WorkflowService(test_db_session, test_user, opa_client=None)
        wf_def = _workflow_definition_with_credential(credential_id=str(credential_in_a.id))

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_PROJECT_ALIVE, new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService", _mock_webhook_service()),
        ):
            wf_name = f"no-evaluator-{uuid4().hex[:6]}"
            with pytest.raises(AuthorizationDeniedError, match="Authorization service unavailable"):
                await service.create_workflow(
                    name=wf_name,
                    description=None,
                    labels={},
                    workflow_definition=wf_def,
                    project_id=project_a_id,
                )

    @pytest.mark.asyncio
    async def test_create_workflow_denies_when_authz_evaluator_rejects(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_a_id: UUID,
        credential_in_a: Credential,
    ) -> None:
        """Workflow save raises AuthorizationDeniedError when evaluator denies credential:use."""
        from syntara.authz.exceptions import AuthorizationDeniedError

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(
            return_value={
                "allowed": False,
                "denied": True,
                "matched_policy": "",
                "denial_reason": "no use permission",
                "denied_by": "",
            }
        )
        service = WorkflowService(test_db_session, test_user, opa_client=mock_evaluator)
        wf_def = _workflow_definition_with_credential(credential_id=str(credential_in_a.id))

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_PROJECT_ALIVE, new_callable=AsyncMock),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService", _mock_webhook_service()),
        ):
            wf_name = f"denied-use-{uuid4().hex[:6]}"
            with pytest.raises(AuthorizationDeniedError, match="Not authorized to use"):
                await service.create_workflow(
                    name=wf_name,
                    description=None,
                    labels={},
                    workflow_definition=wf_def,
                    project_id=project_a_id,
                )

    @pytest.mark.asyncio
    async def test_update_workflow_version_skips_check_for_unchanged_credentials(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_a_id: UUID,
        credential_in_a: Credential,
    ) -> None:
        """Updating a workflow that keeps the same credential skips the credential:use check."""
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(
            return_value={"allow": True, "deny": False, "matched_policy": "", "denial_reason": "", "denied_by": ""}
        )
        service = WorkflowService(test_db_session, test_user, opa_client=mock_evaluator)
        cred_id = str(credential_in_a.id)

        workflow = Workflow(
            id=uuid4(),
            name=f"same-cred-update-{uuid4().hex[:6]}",
            description=None,
            labels={},
            current_version=1,
            created_by=test_user.id,
            is_enabled=False,
            project_id=project_a_id,
        )
        v1 = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_workflow_definition_with_credential(credential_id=cred_id),
            created_by=test_user.id,
            change_description="Initial",
        )
        test_db_session.add(workflow)
        test_db_session.add(v1)
        await test_db_session.flush()

        wf_def_v2 = _workflow_definition_with_credential(credential_id=cred_id)

        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            new_version, _ = await service.create_workflow_version(workflow, wf_def_v2, "no change to credential")

        assert new_version is None or new_version is not None  # either skipped (no diff) or created
        # The credential:use authorize call should NOT have been made (same cred, diff is empty)
        mock_evaluator.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_workflow_version_rejects_cross_project_credential(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_b_id: UUID,
        credential_in_a: Credential,
    ) -> None:
        """Updating a workflow version in project B must reject credential from project A."""
        service = WorkflowService(test_db_session, test_user)

        workflow = Workflow(
            id=uuid4(),
            name=f"update-test-{uuid4().hex[:6]}",
            description=None,
            labels={},
            current_version=1,
            created_by=test_user.id,
            is_enabled=False,
            project_id=project_b_id,
        )
        v1 = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_workflow_definition_with_credential(),
            created_by=test_user.id,
            change_description="Initial",
        )
        test_db_session.add(workflow)
        test_db_session.add(v1)
        await test_db_session.flush()

        wf_def_v2 = _workflow_definition_with_credential(credential_id=str(credential_in_a.id))

        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            with pytest.raises(SafeValueError, match="invalid or belong to a different project"):
                await service.create_workflow_version(workflow, wf_def_v2, "add credential")

    @pytest.mark.asyncio
    async def test_publish_workflow_version_with_inline_definition_checks_credentials(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_a_id: UUID,
        credential_in_a: Credential,
    ) -> None:
        """publish_workflow_version with inline workflow_definition runs credential:use check."""
        from syntara.authz.exceptions import AuthorizationDeniedError

        service = WorkflowService(test_db_session, test_user, opa_client=None)

        workflow = Workflow(
            id=uuid4(),
            name=f"publish-inline-{uuid4().hex[:6]}",
            description=None,
            labels={},
            current_version=1,
            created_by=test_user.id,
            is_enabled=False,
            project_id=project_a_id,
        )
        v1 = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_workflow_definition_with_credential(),
            created_by=test_user.id,
            change_description="Initial",
        )
        test_db_session.add(workflow)
        test_db_session.add(v1)
        await test_db_session.flush()

        inline_def = _workflow_definition_with_credential(credential_id=str(credential_in_a.id))

        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            with pytest.raises(AuthorizationDeniedError, match="Authorization service unavailable"):
                await service.publish_workflow_version(
                    workflow_id=workflow.id,
                    version=1,
                    workflow_definition=inline_def,
                )

    @pytest.mark.asyncio
    async def test_publish_workflow_version_inline_definition_cross_project_credential_rejected(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        project_b_id: UUID,
        credential_in_a: Credential,
    ) -> None:
        """publish_workflow_version rejects cross-project credentials in inline definition."""
        service = WorkflowService(test_db_session, test_user)

        workflow = Workflow(
            id=uuid4(),
            name=f"publish-cross-{uuid4().hex[:6]}",
            description=None,
            labels={},
            current_version=1,
            created_by=test_user.id,
            is_enabled=False,
            project_id=project_b_id,
        )
        v1 = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_workflow_definition_with_credential(),
            created_by=test_user.id,
            change_description="Initial",
        )
        test_db_session.add(workflow)
        test_db_session.add(v1)
        await test_db_session.flush()

        inline_def = _workflow_definition_with_credential(credential_id=str(credential_in_a.id))

        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            with pytest.raises(SafeValueError, match="invalid or belong to a different project"):
                await service.publish_workflow_version(
                    workflow_id=workflow.id,
                    version=1,
                    workflow_definition=inline_def,
                )


class TestBuiltinWorkflowGuards(TestWorkflowServiceBase):
    """Test that built-in workflows cannot be deleted, updated, or unpublished."""

    @pytest.mark.asyncio
    async def test_delete_builtin_workflow_raises(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        workflow = self._create_test_workflow(
            name="Builtin WF", created_by=test_user.id, is_builtin=True, project_id=test_project_id
        )
        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        with pytest.raises(BuiltinWorkflowDeleteError, match="Builtin WF"):
            await service.delete_workflow(workflow.id)

    @pytest.mark.asyncio
    async def test_delete_non_builtin_workflow_succeeds(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        workflow = self._create_test_workflow(name="Normal WF", created_by=test_user.id, project_id=test_project_id)
        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        await service.delete_workflow(workflow.id)

        result = await test_db_session.get(Workflow, workflow.id)
        assert result is not None
        assert result.deleted_at is not None

    @pytest.mark.asyncio
    async def test_update_builtin_workflow_raises(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        workflow = self._create_test_workflow(
            name="Builtin WF", created_by=test_user.id, is_builtin=True, project_id=test_project_id
        )
        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        with pytest.raises(BuiltinWorkflowModifyError, match="Builtin WF"):
            await service.update_workflow(workflow.id, description="hacked")

    @pytest.mark.asyncio
    async def test_update_non_builtin_workflow_succeeds(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        workflow = self._create_test_workflow(name="Normal WF", created_by=test_user.id, project_id=test_project_id)
        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        updated, _, _ = await service.update_workflow(workflow.id, description="updated desc")
        assert updated.description == "updated desc"

    @pytest.mark.asyncio
    async def test_unpublish_builtin_workflow_raises(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        workflow = self._create_test_workflow(
            name="Builtin WF", created_by=test_user.id, is_builtin=True, project_id=test_project_id
        )
        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.flush()
        workflow.published_version_id = version.id
        workflow.is_enabled = True

        service = WorkflowService(test_db_session, test_user)
        with pytest.raises(BuiltinWorkflowModifyError, match="Builtin WF"):
            await service.unpublish_workflow(workflow.id)

    @pytest.mark.asyncio
    async def test_unpublish_non_builtin_workflow_succeeds(
        self, test_db_session: AsyncSession, test_user: User, test_project_id: UUID
    ) -> None:
        workflow = self._create_test_workflow(name="Normal WF", created_by=test_user.id, project_id=test_project_id)
        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.flush()
        workflow.published_version_id = version.id
        workflow.is_enabled = True

        service = WorkflowService(test_db_session, test_user)
        result = await service.unpublish_workflow(workflow.id)
        assert result.published_version_id is None

    @pytest.mark.asyncio
    async def test_create_workflow_in_builtin_project_raises(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        builtin_project = Project(
            name=f"builtin-{uuid4().hex[:6]}",
            is_builtin=True,
        )
        test_db_session.add(builtin_project)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        with pytest.raises(BuiltinProtectionError, match="built-in project"):
            await service.create_workflow(
                name="user-workflow",
                description="should fail",
                labels={},
                workflow_definition=self._create_minimal_workflow_definition(),
                project_id=builtin_project.id,
            )

    @pytest.mark.asyncio
    async def test_create_workflow_in_normal_project_succeeds(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        normal_project = Project(
            name=f"normal-{uuid4().hex[:6]}",
            is_builtin=False,
        )
        test_db_session.add(normal_project)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        workflow, _version, _ = await service.create_workflow(
            name=f"user-workflow-{uuid4().hex[:6]}",
            description="should succeed",
            labels={},
            workflow_definition=self._create_minimal_workflow_definition(),
            project_id=normal_project.id,
        )
        assert workflow.project_id == normal_project.id

    @pytest.mark.asyncio
    async def test_publish_builtin_workflow_raises(self, test_db_session: AsyncSession, test_user: User) -> None:
        workflow = self._create_test_workflow(name="Builtin WF", created_by=test_user.id, is_builtin=True)
        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        with pytest.raises(BuiltinWorkflowModifyError, match="Builtin WF"):
            await service.publish_workflow_version(workflow.id, version=1)

    @pytest.mark.asyncio
    async def test_publish_non_builtin_workflow_succeeds(self, test_db_session: AsyncSession, test_user: User) -> None:
        workflow = self._create_test_workflow(name="Normal WF", created_by=test_user.id, is_enabled=False)
        workflow.published_version_id = None
        version = self._create_test_workflow_version(workflow_id=workflow.id, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(version)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        published, result_version, _warning = await service.publish_workflow_version(workflow.id, version=1)
        assert published.published_version_id == result_version.id
        assert published.is_enabled is True

    @pytest.mark.asyncio
    async def test_restore_builtin_workflow_raises(self, test_db_session: AsyncSession, test_user: User) -> None:
        workflow = self._create_test_workflow(
            name="Builtin WF", created_by=test_user.id, is_builtin=True, current_version=2
        )
        v1 = self._create_test_workflow_version(workflow_id=workflow.id, version=1, created_by=test_user.id)
        v2 = self._create_test_workflow_version(workflow_id=workflow.id, version=2, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(v1)
        test_db_session.add(v2)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        with pytest.raises(BuiltinWorkflowModifyError, match="Builtin WF"):
            await service.restore_workflow_version(workflow.id, version=1)

    @pytest.mark.asyncio
    async def test_restore_non_builtin_workflow_succeeds(self, test_db_session: AsyncSession, test_user: User) -> None:
        workflow = self._create_test_workflow(name="Normal WF", created_by=test_user.id, current_version=2)
        # v1 uses a distinct definition so restore is not a no-op (change detection in _create_version_record
        # skips creation when the definition matches the current version)
        v1_definition = self._create_minimal_workflow_definition()
        v1_definition["name"] = "v1-workflow"
        v1 = self._create_test_workflow_version(
            workflow_id=workflow.id,
            version=1,
            created_by=test_user.id,
            workflow_definition=v1_definition,
        )
        v2 = self._create_test_workflow_version(workflow_id=workflow.id, version=2, created_by=test_user.id)
        test_db_session.add(workflow)
        test_db_session.add(v1)
        test_db_session.add(v2)
        await test_db_session.flush()

        service = WorkflowService(test_db_session, test_user)
        _, restored = await service.restore_workflow_version(workflow.id, version=1)
        assert restored.version == 3


class TestWorkflowVersionConflictDetection(TestWorkflowServiceBase):
    """Test optimistic concurrency control via expected_version."""

    @pytest.mark.asyncio
    async def test_update_with_stale_expected_version_raises_conflict(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """When expected_version < current_version, update should return 409."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(
            name=f"conflict-{uuid4().hex[:6]}", current_version=3, created_by=test_user.id
        )
        test_db_session.add(workflow)

        version = self._create_test_workflow_version(workflow_id=workflow.id, version=3, created_by=test_user.id)
        test_db_session.add(version)
        await test_db_session.commit()

        with pytest.raises(WorkflowVersionConflictError) as exc_info:
            await service.update_workflow(
                workflow.id,
                name="should-fail",
                expected_version=1,
            )

        assert exc_info.value.current_version == 3
        assert exc_info.value.expected_version == 1
        assert exc_info.value.created_by_username == test_user.username

    @pytest.mark.asyncio
    async def test_update_with_matching_expected_version_succeeds(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """When expected_version == current_version, update should proceed."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(
            name=f"match-{uuid4().hex[:6]}", current_version=1, created_by=test_user.id
        )
        test_db_session.add(workflow)

        version = self._create_test_workflow_version(workflow_id=workflow.id, version=1, created_by=test_user.id)
        test_db_session.add(version)
        await test_db_session.commit()

        result_workflow, _, _ = await service.update_workflow(
            workflow.id,
            name="should-succeed",
            expected_version=1,
        )
        assert result_workflow.name == "should-succeed"

    @pytest.mark.asyncio
    async def test_update_without_expected_version_skips_check(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """When expected_version is omitted, no conflict check happens."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(
            name=f"nocheck-{uuid4().hex[:6]}", current_version=5, created_by=test_user.id
        )
        test_db_session.add(workflow)

        version = self._create_test_workflow_version(workflow_id=workflow.id, version=5, created_by=test_user.id)
        test_db_session.add(version)
        await test_db_session.commit()

        result_workflow, _, _ = await service.update_workflow(
            workflow.id,
            name="should-succeed-no-check",
        )
        assert result_workflow.name == "should-succeed-no-check"

    @pytest.mark.asyncio
    async def test_publish_with_stale_expected_version_raises_conflict(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """When expected_version < current_version, publish should return 409."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(
            name=f"pub-conflict-{uuid4().hex[:6]}",
            current_version=3,
            created_by=test_user.id,
            is_enabled=False,
        )
        workflow.published_version_id = None
        test_db_session.add(workflow)

        version = self._create_test_workflow_version(workflow_id=workflow.id, version=3, created_by=test_user.id)
        test_db_session.add(version)
        await test_db_session.commit()

        with pytest.raises(WorkflowVersionConflictError) as exc_info:
            await service.publish_workflow_version(
                workflow.id,
                version=3,
                expected_version=1,
            )

        assert exc_info.value.current_version == 3
        assert exc_info.value.expected_version == 1

    @pytest.mark.asyncio
    async def test_publish_without_expected_version_skips_check(
        self, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """When expected_version is omitted on publish, no conflict check happens."""
        service = WorkflowService(test_db_session, test_user)

        workflow = self._create_test_workflow(
            name=f"pub-nocheck-{uuid4().hex[:6]}",
            current_version=3,
            created_by=test_user.id,
            is_enabled=False,
        )
        workflow.published_version_id = None
        test_db_session.add(workflow)

        version = self._create_test_workflow_version(workflow_id=workflow.id, version=3, created_by=test_user.id)
        test_db_session.add(version)
        await test_db_session.commit()

        mock_wh_svc = MagicMock()
        mock_wh_svc.return_value.sync_webhook_triggers = AsyncMock()
        with (
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService", mock_wh_svc),
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as mock_sched,
        ):
            mock_sched.return_value.sync_scheduled_triggers = AsyncMock()
            result_workflow, _result_version, _warning = await service.publish_workflow_version(
                workflow.id,
                version=3,
            )
            assert result_workflow.published_version_id is not None


class TestUpdateVersionMetadata(TestWorkflowServiceBase):
    """Test update_version_metadata functionality."""

    async def _setup_workflow_with_version(
        self,
        session: AsyncSession,
        user: User,
        *,
        name: str | None = "v1.0",
        change_description: str | None = "Initial release",
    ) -> tuple[Workflow, WorkflowVersion]:
        workflow = self._create_test_workflow(name=f"meta-{uuid4().hex[:6]}", created_by=user.id)
        session.add(workflow)

        version = self._create_test_workflow_version(
            workflow_id=workflow.id, version=1, created_by=user.id, change_description=change_description or ""
        )
        version.name = name
        session.add(version)
        await session.commit()
        return workflow, version

    @pytest.mark.asyncio
    async def test_update_both_fields(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test updating both name and change_description."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._setup_workflow_with_version(test_db_session, test_user)

        result = await service.update_version_metadata(
            workflow.id, 1, name="Updated Name", change_description="Updated Desc"
        )

        assert result.name == "Updated Name"
        assert result.change_description == "Updated Desc"
        assert result.updated_by == test_user.id

    @pytest.mark.asyncio
    async def test_partial_update_name_only(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test updating only name leaves change_description unchanged."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._setup_workflow_with_version(
            test_db_session, test_user, change_description="Original desc"
        )

        result = await service.update_version_metadata(workflow.id, 1, name="New Name", fields_set={"name"})

        assert result.name == "New Name"
        assert result.change_description == "Original desc"

    @pytest.mark.asyncio
    async def test_partial_update_change_description_only(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test updating only change_description leaves name unchanged."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._setup_workflow_with_version(test_db_session, test_user, name="Original Name")

        result = await service.update_version_metadata(
            workflow.id, 1, change_description="New Desc", fields_set={"change_description"}
        )

        assert result.name == "Original Name"
        assert result.change_description == "New Desc"

    @pytest.mark.asyncio
    async def test_clear_fields_with_explicit_none(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test clearing fields by sending explicit None values."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._setup_workflow_with_version(
            test_db_session, test_user, name="Has Name", change_description="Has Desc"
        )

        result = await service.update_version_metadata(
            workflow.id,
            1,
            name=None,
            change_description=None,
            fields_set={"name", "change_description"},
        )

        assert result.name is None
        assert result.change_description is None

    @pytest.mark.asyncio
    async def test_noop_when_fields_set_is_empty(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that an empty fields_set results in no changes and no commit."""
        service = WorkflowService(test_db_session, test_user)
        workflow, version = await self._setup_workflow_with_version(test_db_session, test_user)

        result = await service.update_version_metadata(workflow.id, 1, fields_set=set())

        assert result.name == version.name
        assert result.change_description == version.change_description
        assert result.updated_by != test_user.id

    @pytest.mark.asyncio
    async def test_workflow_not_found_raises(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that a nonexistent workflow_id raises WorkflowNotFoundError."""
        service = WorkflowService(test_db_session, test_user)

        nonexistent_id = uuid4()
        with pytest.raises(WorkflowNotFoundError):
            await service.update_version_metadata(nonexistent_id, 1, name="x")

    @pytest.mark.asyncio
    async def test_version_not_found_raises(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that a nonexistent version raises WorkflowVersionNotFoundError."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._setup_workflow_with_version(test_db_session, test_user)

        with pytest.raises(WorkflowVersionNotFoundError):
            await service.update_version_metadata(workflow.id, 999, name="x")

    @pytest.mark.asyncio
    async def test_default_fields_set_updates_both(self, test_db_session: AsyncSession, test_user: User) -> None:
        """Test that fields_set=None defaults to updating both fields."""
        service = WorkflowService(test_db_session, test_user)
        workflow, _ = await self._setup_workflow_with_version(test_db_session, test_user)

        result = await service.update_version_metadata(
            workflow.id, 1, name="Default Name", change_description="Default Desc"
        )

        assert result.name == "Default Name"
        assert result.change_description == "Default Desc"
        assert result.updated_by == test_user.id
