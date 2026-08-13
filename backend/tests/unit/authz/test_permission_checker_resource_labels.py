"""Unit tests for authorization dependencies.

Covers ``PermissionChecker``, ``ProjectScopeFilter``, and ``VisibilityFilter``
with focus on resource label resolution and authorization decision paths.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.exceptions import RequestValidationError

from syntara.authz.dependencies import PermissionChecker, ProjectScopeFilter, VisibilityFilter
from syntara.authz.engine import AllowedProjectsResult, AuthzResult, VisibilityResult
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.credentials.models.credential import Credential


def _mock_db_with_results(*results: object) -> AsyncMock:
    """Return a mock AsyncSession whose exec() returns results in sequence.

    Each result is wrapped in a MagicMock with a .first() method.
    """
    db = AsyncMock()
    side_effects = []
    for r in results:
        mock_result = MagicMock()
        mock_result.first.return_value = r
        side_effects.append(mock_result)
    db.exec = AsyncMock(side_effect=side_effects)
    return db


class TestResolveProjectFromResource:
    """Test _resolve_project_from_resource returns project name."""

    @pytest.fixture
    def checker(self) -> PermissionChecker:
        return PermissionChecker(
            "credential",
            "read",
            resource_model=Credential,
            resource_id_param="credential_id",
        )

    async def test_no_model_returns_empty(self) -> None:
        checker = PermissionChecker("credential", "read")
        db = AsyncMock()
        result = await checker._resolve_project_from_resource(db, str(uuid4()))
        assert result == ""

    async def test_empty_resource_id_returns_empty(self, checker: PermissionChecker) -> None:
        db = AsyncMock()
        result = await checker._resolve_project_from_resource(db, "")
        assert result == ""

    async def test_invalid_uuid_raises(self, checker: PermissionChecker) -> None:
        db = AsyncMock()
        with pytest.raises(RequestValidationError):
            await checker._resolve_project_from_resource(db, "not-a-uuid")

    async def test_no_row_returns_empty(self, checker: PermissionChecker) -> None:
        db = _mock_db_with_results(None)
        result = await checker._resolve_project_from_resource(db, str(uuid4()))
        assert result == ""

    async def test_row_with_project_id(self, checker: PermissionChecker) -> None:
        project_id = uuid4()
        db = _mock_db_with_results(project_id, "my-project")
        result = await checker._resolve_project_from_resource(db, str(uuid4()))
        assert result == "my-project"


class TestResolveResourceLabels:
    """Test _resolve_resource_labels returns labels dict."""

    @pytest.fixture
    def checker(self) -> PermissionChecker:
        return PermissionChecker(
            "credential",
            "read",
            resource_model=Credential,
            resource_id_param="credential_id",
        )

    async def test_no_model_returns_empty(self) -> None:
        checker = PermissionChecker("credential", "read")
        db = AsyncMock()
        result = await checker._resolve_resource_labels(db, str(uuid4()))
        assert result == {}

    async def test_empty_resource_id_returns_empty(self, checker: PermissionChecker) -> None:
        db = AsyncMock()
        result = await checker._resolve_resource_labels(db, "")
        assert result == {}

    async def test_invalid_uuid_raises(self, checker: PermissionChecker) -> None:
        db = AsyncMock()
        with pytest.raises(RequestValidationError):
            await checker._resolve_resource_labels(db, "not-a-uuid")

    async def test_no_row_returns_empty(self, checker: PermissionChecker) -> None:
        db = _mock_db_with_results(None)
        result = await checker._resolve_resource_labels(db, str(uuid4()))
        assert result == {}

    async def test_returns_labels(self, checker: PermissionChecker) -> None:
        labels = {"env": "production", "team": "platform"}
        db = _mock_db_with_results(labels)
        result = await checker._resolve_resource_labels(db, str(uuid4()))
        assert result == labels


class TestResolveResourceProjectIncludesLabels:
    """Test _resolve_resource_project returns 4-tuple with name and labels."""

    async def test_no_resource_model_empty_labels(self) -> None:
        checker = PermissionChecker("credential", "create", body_project_field="project_id")
        request = MagicMock()
        request.path_params = {}
        request.json = AsyncMock(return_value={"project_id": None})
        db = AsyncMock()

        _, _, _, resource_labels = await checker._resolve_resource_project(request, db)
        assert resource_labels == {}

    async def test_resource_model_threads_labels(self) -> None:
        checker = PermissionChecker(
            "credential",
            "read",
            resource_model=Credential,
            resource_id_param="credential_id",
        )
        resource_id = str(uuid4())
        project_id = uuid4()
        expected_labels = {"env": "production"}
        request = MagicMock()
        request.path_params = {"credential_id": resource_id}

        db = _mock_db_with_results(
            project_id,
            "my-project",
            expected_labels,
            "my-credential",
        )
        rid, rname, rproject, rlabels = await checker._resolve_resource_project(request, db)
        assert rid == resource_id
        assert rname == "my-credential"
        assert rproject == "my-project"
        assert rlabels == expected_labels

    async def test_project_param_path_empty_labels(self) -> None:
        checker = PermissionChecker("project", "update", project_param="project_id")
        project_id = str(uuid4())
        request = MagicMock()
        request.path_params = {"project_id": project_id}

        db = _mock_db_with_results("my-project")
        _, _, _, resource_labels = await checker._resolve_resource_project(request, db)
        assert resource_labels == {}

    async def test_project_type_uses_project_id_as_resource_id(self) -> None:
        checker = PermissionChecker("project", "update", project_param="project_id")
        project_id = str(uuid4())
        request = MagicMock()
        request.path_params = {"project_id": project_id}

        db = _mock_db_with_results("my-project")
        rid, _rname, rproject, _ = await checker._resolve_resource_project(request, db)
        assert rid == project_id
        assert rproject == "my-project"

    async def test_labels_fetched_when_project_resolved_via_path(self) -> None:
        """Labels should be fetched even when project comes from project_param."""
        checker = PermissionChecker(
            "credential",
            "read",
            project_param="project_id",
            resource_model=Credential,
            resource_id_param="credential_id",
        )
        credential_id = str(uuid4())
        project_id = str(uuid4())
        expected_labels = {"env": "production"}
        request = MagicMock()
        request.path_params = {"project_id": project_id, "credential_id": credential_id}

        db = _mock_db_with_results("my-project", expected_labels, "my-credential")
        rid, _rname, rproject, rlabels = await checker._resolve_resource_project(request, db)
        assert rid == credential_id
        assert rproject == "my-project"
        assert rlabels == expected_labels


class TestResolveProjectFromPath:
    """Test _resolve_project_from_path handles project lookup and not-found."""

    async def test_no_project_id_in_params(self) -> None:
        checker = PermissionChecker("project", "update", project_param="project_id")
        request = MagicMock()
        request.path_params = {}
        db = AsyncMock()

        result = await checker._resolve_project_from_path(request, db)
        assert result == ""

    async def test_project_not_found_raises(self) -> None:
        from syntara.authz.exceptions import ProjectNotFoundError

        checker = PermissionChecker("project", "update", project_param="project_id")
        request = MagicMock()
        request.path_params = {"project_id": str(uuid4())}

        db = _mock_db_with_results(None)
        with pytest.raises(ProjectNotFoundError):
            await checker._resolve_project_from_path(request, db)

    async def test_project_found_returns_name(self) -> None:
        checker = PermissionChecker("credential", "read", project_param="project_id")
        request = MagicMock()
        request.path_params = {"project_id": str(uuid4())}

        db = _mock_db_with_results("my-project")
        result = await checker._resolve_project_from_path(request, db)
        assert result == "my-project"


class TestResolveProjectFromBody:
    """Test _resolve_project_from_body with valid project IDs."""

    async def test_body_with_valid_project_id(self) -> None:
        checker = PermissionChecker("credential", "create", body_project_field="project_id")
        request = MagicMock()
        request.json = AsyncMock(return_value={"project_id": str(uuid4())})

        db = _mock_db_with_results("my-project")
        result = await checker._resolve_project_from_body(request, db)
        assert result == "my-project"

    async def test_body_with_project_not_found_raises(self) -> None:
        from syntara.authz.exceptions import ProjectNotFoundError

        checker = PermissionChecker("credential", "create", body_project_field="project_id")
        request = MagicMock()
        request.json = AsyncMock(return_value={"project_id": str(uuid4())})

        db = _mock_db_with_results(None)
        with pytest.raises(ProjectNotFoundError):
            await checker._resolve_project_from_body(request, db)


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.labels = {}
    user.authz_metadata = {}
    return user


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.app.state.authz_evaluator = MagicMock()
    request.state.is_cert_authenticated = False
    return request


def _allowed_result() -> AuthzResult:
    return AuthzResult(
        allowed=True,
        denied=False,
        matched_policy="test",
        denial_reason="",
        denied_by="",
        effective_policies=[],
    )


def _denied_result() -> AuthzResult:
    return AuthzResult(
        allowed=False,
        denied=True,
        matched_policy="",
        denial_reason="policy_deny",
        denied_by="deny-policy",
        effective_policies=[],
    )


class TestCallPassesResourceLabels:
    """Test __call__ passes resource_labels through to AuthzRequest."""

    async def test_call_passes_labels_to_authorize(self) -> None:
        checker = PermissionChecker(
            "credential",
            "read",
            resource_model=Credential,
            resource_id_param="credential_id",
        )
        resource_id = str(uuid4())
        expected_labels = {"env": "production"}

        request = _mock_request()
        request.path_params = {"credential_id": resource_id}
        current_user = _mock_user()

        with (
            patch.object(
                checker,
                "_resolve_resource_project",
                new_callable=AsyncMock,
                return_value=(resource_id, "my-credential", "my-project", expected_labels),
            ),
            patch(
                "syntara.authz.dependencies.authorize",
                new_callable=AsyncMock,
                return_value=_allowed_result(),
            ) as mock_authorize,
        ):
            await checker(request, current_user, AsyncMock())

            authz_request = mock_authorize.call_args[0][2]
            assert authz_request.resource_labels == expected_labels

    async def test_call_raises_when_denied(self) -> None:
        checker = PermissionChecker("credential", "read")
        request = _mock_request()
        current_user = _mock_user()
        mock_session = AsyncMock()

        with (
            patch.object(
                checker,
                "_resolve_resource_project",
                new_callable=AsyncMock,
                return_value=("", "", "", {}),
            ),
            patch(
                "syntara.authz.dependencies.authorize",
                new_callable=AsyncMock,
                return_value=_denied_result(),
            ),
            pytest.raises(AuthorizationDeniedError),
        ):
            await checker(request, current_user, mock_session)


class TestProjectScopeFilter:
    """Test ProjectScopeFilter dependency."""

    async def test_calls_resolve_allowed_projects(self) -> None:
        scope_filter = ProjectScopeFilter("credential", "read")
        request = _mock_request()
        current_user = _mock_user()

        expected = AllowedProjectsResult(all_projects=True, project_ids=[])
        with patch(
            "syntara.authz.dependencies.resolve_allowed_projects",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_resolve:
            result = await scope_filter(request, current_user, AsyncMock())

            assert result == expected
            mock_resolve.assert_called_once()


class TestVisibilityFilter:
    """Test VisibilityFilter dependency."""

    async def test_calls_resolve_visibility(self) -> None:
        vis_filter = VisibilityFilter("credential", "read")
        request = _mock_request()
        current_user = _mock_user()

        expected = VisibilityResult(unrestricted=True)
        with patch(
            "syntara.authz.dependencies.resolve_visibility",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_resolve:
            result = await vis_filter(request, current_user, AsyncMock())

            assert result == expected
            mock_resolve.assert_called_once()
