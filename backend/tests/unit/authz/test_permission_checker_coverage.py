"""Unit tests for PermissionChecker edge cases to improve coverage.

Tests certificate authentication bypasses, form field resolution,
resource owner resolution, and error handling paths.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.exceptions import RequestValidationError

from syntara.authz.dependencies import PermissionChecker, ProjectScopeFilter, VisibilityFilter
from syntara.authz.engine import AllowedProjectsResult, VisibilityResult
from syntara.core.models.user import User

# ============================================================================
# Certificate authentication bypasses
# ============================================================================


class TestCertificateAuthenticationBypass:
    """Verify that cert-authenticated requests bypass authz checks."""

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """Return a request marked as cert-authenticated."""
        request = MagicMock()
        request.state.is_cert_authenticated = True
        request.path_params = {}
        request.app.state.authz_evaluator = MagicMock()
        return request

    @pytest.fixture
    def mock_user(self) -> User:
        """Return a mock user."""
        return User(
            id=uuid4(),
            username="testuser",
            email="test@example.com",
            labels={},
            authz_metadata={},
        )

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database session."""
        return AsyncMock()

    async def test_permission_checker_bypasses_cert_auth(
        self, mock_request: MagicMock, mock_user: User, mock_db: AsyncMock
    ) -> None:
        """PermissionChecker returns early when request is cert-authenticated."""
        checker = PermissionChecker("workflow", "read")
        # Should return None without calling evaluator
        assert await checker(mock_request, mock_user, mock_db) is None  # type: ignore[func-returns-value]

    async def test_project_scope_filter_bypasses_cert_auth(
        self, mock_request: MagicMock, mock_user: User, mock_db: AsyncMock
    ) -> None:
        """ProjectScopeFilter returns all_projects=True when cert-authenticated."""
        filter_dep = ProjectScopeFilter("credential", "read")
        result = await filter_dep(mock_request, mock_user, mock_db)
        assert isinstance(result, AllowedProjectsResult)
        assert result.all_projects is True
        assert result.project_ids == []

    async def test_visibility_filter_bypasses_cert_auth(
        self, mock_request: MagicMock, mock_user: User, mock_db: AsyncMock
    ) -> None:
        """VisibilityFilter returns unrestricted=True when cert-authenticated."""
        filter_dep = VisibilityFilter("credential", "read")
        result = await filter_dep(mock_request, mock_user, mock_db)
        assert isinstance(result, VisibilityResult)
        assert result.unrestricted is True


# ============================================================================
# Form field resolution
# ============================================================================


class TestResolveProjectFromForm:
    """Test multipart form field project resolution."""

    @pytest.fixture
    def checker(self) -> PermissionChecker:
        """Return a checker configured with form_project_field."""
        return PermissionChecker("credential", "create", form_project_field="project_id")

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database session."""
        db = AsyncMock()

        # Mock the project name lookup
        result_mock = MagicMock()
        result_mock.first.return_value = "test-project"
        db.exec.return_value = result_mock
        return db

    @pytest.fixture
    def mock_request_with_form(self) -> MagicMock:
        """Return a request with multipart form data."""
        request = MagicMock()
        project_id = str(uuid4())

        async def mock_form() -> dict[str, str]:
            return {"project_id": project_id}

        request.form = mock_form
        request.path_params = {}
        return request

    async def test_resolve_project_from_form_valid(
        self, checker: PermissionChecker, mock_request_with_form: MagicMock, mock_db: AsyncMock
    ) -> None:
        """Form field with valid project ID resolves to project name."""
        result = await checker._resolve_project_from_form(mock_request_with_form, mock_db)
        assert result == "test-project"

    async def test_resolve_project_from_form_no_field(
        self, mock_request_with_form: MagicMock, mock_db: AsyncMock
    ) -> None:
        """Returns empty string when form_project_field is None."""
        checker = PermissionChecker("credential", "create")  # No form_project_field
        result = await checker._resolve_project_from_form(mock_request_with_form, mock_db)
        assert result == ""

    async def test_resolve_project_from_form_missing_value(
        self, checker: PermissionChecker, mock_db: AsyncMock
    ) -> None:
        """Returns empty string when form field value is missing."""
        request = MagicMock()

        async def mock_form() -> dict[str, str]:
            return {}  # No project_id field

        request.form = mock_form
        result = await checker._resolve_project_from_form(request, mock_db)
        assert result == ""

    async def test_resolve_project_from_form_non_string_value(
        self, checker: PermissionChecker, mock_db: AsyncMock
    ) -> None:
        """Returns empty string when form field value is not a string."""
        request = MagicMock()

        async def mock_form() -> dict[str, object]:
            return {"project_id": 123}  # Not a string

        request.form = mock_form
        result = await checker._resolve_project_from_form(request, mock_db)
        assert result == ""

    async def test_resolve_project_from_form_project_not_found(
        self, checker: PermissionChecker, mock_request_with_form: MagicMock
    ) -> None:
        """Raises ProjectNotFoundError when project doesn't exist."""
        from syntara.authz.exceptions import ProjectNotFoundError

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.first.return_value = None  # Project not found
        db.exec.return_value = result_mock

        with pytest.raises(ProjectNotFoundError, match="not found"):
            await checker._resolve_project_from_form(mock_request_with_form, db)


# ============================================================================
# Resource owner resolution
# ============================================================================


class TestResolveResourceOwner:
    """Test resource owner (created_by) field resolution."""

    @pytest.fixture
    def checker_with_owner(self) -> PermissionChecker:
        """Return a checker configured with owner_field."""
        from syntara.credentials.models.credential import Credential

        return PermissionChecker(
            "credential", "update", resource_model=Credential, resource_id_param="id", owner_field="created_by"
        )

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database session."""
        db = AsyncMock()
        owner_id = uuid4()
        result_mock = MagicMock()
        result_mock.first.return_value = owner_id
        db.exec.return_value = result_mock
        return db

    async def test_resolve_owner_valid(self, checker_with_owner: PermissionChecker, mock_db: AsyncMock) -> None:
        """Resolves owner ID when resource exists."""
        resource_id = str(uuid4())
        owner = await checker_with_owner._resolve_resource_owner(mock_db, resource_id)
        assert owner != ""
        # Should return a string UUID
        assert len(owner) > 0

    async def test_resolve_owner_no_owner_field(self, mock_db: AsyncMock) -> None:
        """Returns empty string when owner_field is None."""
        from syntara.credentials.models.credential import Credential

        checker = PermissionChecker("credential", "read", resource_model=Credential, resource_id_param="id")
        result = await checker._resolve_resource_owner(mock_db, str(uuid4()))
        assert result == ""

    async def test_resolve_owner_no_resource_model(self, mock_db: AsyncMock) -> None:
        """Returns empty string when resource_model is None."""
        checker = PermissionChecker("credential", "read", owner_field="created_by")
        result = await checker._resolve_resource_owner(mock_db, str(uuid4()))
        assert result == ""

    async def test_resolve_owner_no_resource_id(
        self, checker_with_owner: PermissionChecker, mock_db: AsyncMock
    ) -> None:
        """Returns empty string when resource_id is empty."""
        result = await checker_with_owner._resolve_resource_owner(mock_db, "")
        assert result == ""

    async def test_resolve_owner_invalid_uuid(self, checker_with_owner: PermissionChecker, mock_db: AsyncMock) -> None:
        """Returns empty string when resource_id is not a valid UUID."""
        result = await checker_with_owner._resolve_resource_owner(mock_db, "not-a-uuid")
        assert result == ""

    async def test_resolve_owner_model_missing_owner_field(self) -> None:
        """Returns empty string when model doesn't have the owner_field attribute."""
        from syntara.workflows.models.workflow import Workflow

        # Workflow doesn't have created_by field
        checker = PermissionChecker(
            "workflow", "read", resource_model=Workflow, resource_id_param="id", owner_field="created_by"
        )
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.first.return_value = None
        db.exec.return_value = result_mock

        result = await checker._resolve_resource_owner(db, str(uuid4()))
        assert result == ""

    async def test_resolve_owner_not_found(self, checker_with_owner: PermissionChecker) -> None:
        """Returns empty string when resource doesn't exist."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.first.return_value = None  # No owner found
        db.exec.return_value = result_mock

        result = await checker_with_owner._resolve_resource_owner(db, str(uuid4()))
        assert result == ""


# ============================================================================
# Resource name resolution edge cases
# ============================================================================


class TestResolveResourceName:
    """Test resource name resolution edge cases."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database session."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.first.return_value = "test-resource"
        db.exec.return_value = result_mock
        return db

    async def test_resolve_name_model_not_named_resource(self) -> None:
        """Returns empty string when model is not a subclass of NamedResource."""
        from syntara.core.models.base import BaseResource

        # BaseResource is not a NamedResource subclass
        checker = PermissionChecker("test", "read", resource_model=BaseResource, resource_id_param="id")
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.first.return_value = None
        db.exec.return_value = result_mock

        result = await checker._resolve_resource_name(db, str(uuid4()))
        assert result == ""

    async def test_resolve_name_invalid_uuid(self, mock_db: AsyncMock) -> None:
        """Raises RequestValidationError when resource_id is not a valid UUID."""
        from syntara.workflows.models.workflow import Workflow

        checker = PermissionChecker("workflow", "read", resource_model=Workflow, resource_id_param="id")
        with pytest.raises(RequestValidationError) as exc_info:
            await checker._resolve_resource_name(mock_db, "not-a-uuid")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "uuid_parsing"
        assert "Invalid UUID format" in errors[0]["msg"]


# ============================================================================
# Authz metrics recording error handling
# ============================================================================


class TestAuthzMetricsErrorHandling:
    """Test that authz metrics recording failures don't break requests."""

    async def test_metrics_recording_error_suppressed(self) -> None:
        """Metric recording errors are logged but don't raise."""
        from syntara.authz.dependencies import _record_authz_duration

        # Should not raise even if metrics recorder is unavailable
        _record_authz_duration(0.0, "workflow", "read")
        # If we get here without exception, the test passes


# ============================================================================
# Additional coverage for edge cases
# ============================================================================


class TestResolveProjectFromPathEdgeCases:
    """Test _resolve_project_from_path edge cases."""

    async def test_resolve_project_from_path_no_param(self) -> None:
        """Returns empty string when project_param is None."""
        checker = PermissionChecker("workflow", "read")  # No project_param
        request = MagicMock()
        request.path_params = {}
        db = AsyncMock()

        result = await checker._resolve_project_from_path(request, db)
        assert result == ""


class TestOwnerFieldResolution:
    """Test owner_field resolution in __call__."""

    async def test_owner_field_not_populated_when_no_resource_id(self) -> None:
        """Owner metadata is not populated when resource_id is empty."""
        from syntara.credentials.models.credential import Credential

        checker = PermissionChecker("credential", "update", resource_model=Credential, owner_field="created_by")

        request = MagicMock()
        request.state.is_cert_authenticated = False
        request.path_params = {}  # No resource ID
        request.app.state.authz_evaluator = MagicMock()

        user = User(id=uuid4(), username="test", email="test@example.com", labels={}, authz_metadata={})

        db = AsyncMock()
        # Mock authorize to allow the request
        from unittest.mock import patch

        with patch("syntara.authz.dependencies.authorize") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=True)
            result_mock = MagicMock()
            result_mock.first.return_value = None
            db.exec.return_value = result_mock

            await checker(request, user, db)

            # Verify that authorize was called
            assert mock_authorize.called
            # Get the authz_request that was passed
            authz_request = mock_authorize.call_args[0][2]
            # Verify that resource_metadata is empty (no owner_field populated)
            assert authz_request.resource_metadata == {}
