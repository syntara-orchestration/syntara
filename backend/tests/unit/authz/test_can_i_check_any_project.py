"""Unit tests for can_i check_any_project wiring (AAP-83294)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.engine import AuthzRequest, AuthzResult
from syntara.authz.router import CanIRequest, can_i


class TestCanIRequestModel:
    """CanIRequest exposes check_any_project with a safe default."""

    def test_default_check_any_project_is_false(self) -> None:
        body = CanIRequest(action="read", resource_type="role-assignment")
        assert body.check_any_project is False

    def test_check_any_project_can_be_enabled(self) -> None:
        body = CanIRequest(
            action="read",
            resource_type="service_account",
            check_any_project=True,
        )
        assert body.check_any_project is True

    def test_rejects_mixed_check_any_project_and_resource_project(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="check_any_project cannot be combined"):
            CanIRequest(
                action="read",
                resource_type="role-assignment",
                resource_project="my-project",
                check_any_project=True,
            )


class TestCanIEndpointWiring:
    """can_i forwards check_any_project into AuthzRequest."""

    @pytest.mark.asyncio
    async def test_forwards_check_any_project_true(self) -> None:
        body = CanIRequest(
            action="read",
            resource_type="role-assignment",
            check_any_project=True,
        )
        user = MagicMock()
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        db = AsyncMock()
        evaluator = AsyncMock()
        authz_result = AuthzResult(
            allowed=True,
            denied=False,
            matched_policy="role-assignment:read:project",
            denial_reason="",
            denied_by="",
            effective_policies=[],
        )

        with (
            patch("syntara.authz.router._resolve_project_input", new=AsyncMock(return_value="")),
            patch("syntara.authz.router.authorize", new=AsyncMock(return_value=authz_result)) as mock_authorize,
        ):
            response = await can_i(body, user, db, evaluator)

        assert response.allowed is True
        assert mock_authorize.await_args is not None
        request = mock_authorize.await_args.args[2]
        assert isinstance(request, AuthzRequest)
        assert request.check_any_project is True
        assert request.action == "read"
        assert request.resource_type == "role-assignment"

    @pytest.mark.asyncio
    async def test_forwards_check_any_project_false_by_default(self) -> None:
        body = CanIRequest(action="read", resource_type="project")
        user = MagicMock()
        user.id = uuid4()
        user.labels = {}
        user.authz_metadata = {}
        db = AsyncMock()
        evaluator = AsyncMock()
        authz_result = AuthzResult(
            allowed=False,
            denied=False,
            matched_policy="",
            denial_reason="",
            denied_by="",
            effective_policies=[],
        )

        with (
            patch("syntara.authz.router._resolve_project_input", new=AsyncMock(return_value="")),
            patch("syntara.authz.router.authorize", new=AsyncMock(return_value=authz_result)) as mock_authorize,
        ):
            await can_i(body, user, db, evaluator)

        assert mock_authorize.await_args is not None
        request = mock_authorize.await_args.args[2]
        assert request.check_any_project is False


class TestPermissionCheckerNeverSetsAnyProject:
    """Enforcement path must not set check_any_project (advisory can_i only)."""

    @pytest.mark.asyncio
    async def test_permission_checker_authz_request_keeps_flag_false(self) -> None:
        from syntara.authz.dependencies import PermissionChecker

        checker = PermissionChecker("credential", "read")
        request = MagicMock()
        request.state = MagicMock()
        request.state.is_cert_authenticated = False
        request.path_params = {}
        user = MagicMock()
        user.id = uuid4()
        user.username = "u"
        user.labels = {}
        user.authz_metadata = {}

        with (
            patch.object(
                checker,
                "_resolve_resource_project",
                new=AsyncMock(return_value=("", "", "", {})),
            ),
            patch(
                "syntara.authz.dependencies.authorize",
                new=AsyncMock(
                    return_value=AuthzResult(
                        allowed=True,
                        denied=False,
                        matched_policy="",
                        denial_reason="",
                        denied_by="",
                        effective_policies=[],
                    )
                ),
            ) as mock_authorize,
            patch("syntara.authz.dependencies.get_authz_evaluator", return_value=AsyncMock()),
        ):
            await checker(request, user, AsyncMock())

        assert mock_authorize.await_args is not None
        authz_request = mock_authorize.await_args.args[2]
        assert isinstance(authz_request, AuthzRequest)
        assert authz_request.check_any_project is False


class TestAuthorizeAnyProjectInput:
    """authorize() puts check_any_project on Rego input.resource.any_project."""

    @pytest.mark.asyncio
    async def test_rego_input_includes_any_project_true(self) -> None:
        from syntara.authz.engine import authorize

        db = AsyncMock()
        evaluator = AsyncMock()
        user_id = uuid4()
        request = AuthzRequest(
            user_id=user_id,
            action="read",
            resource_type="service_account",
            resource_id="",
            check_any_project=True,
            groups=[],
        )

        with (
            patch("syntara.authz.engine.resolve_effective_policies", new=AsyncMock(return_value=[])),
            patch(
                "syntara.authz.engine._evaluate_authz_policy",
                new=AsyncMock(
                    return_value={
                        "allow": True,
                        "deny": False,
                        "matched_policy": "service_account:read:project",
                        "denial_reason": "",
                        "denied_by": "",
                    }
                ),
            ) as mock_eval,
        ):
            result = await authorize(db, evaluator, request)

        assert result.allowed is True
        assert mock_eval.await_args is not None
        authz_input = mock_eval.await_args.args[1]
        assert authz_input["resource"]["any_project"] is True
        assert authz_input["resource"]["project"] == ""

    @pytest.mark.asyncio
    async def test_rego_input_includes_any_project_false(self) -> None:
        from syntara.authz.engine import authorize

        db = AsyncMock()
        evaluator = AsyncMock()
        request = AuthzRequest(
            user_id=uuid4(),
            action="read",
            resource_type="service_account",
            resource_id="",
            check_any_project=False,
            groups=[],
        )

        with (
            patch("syntara.authz.engine.resolve_effective_policies", new=AsyncMock(return_value=[])),
            patch(
                "syntara.authz.engine._evaluate_authz_policy",
                new=AsyncMock(
                    return_value={
                        "allow": False,
                        "deny": False,
                        "matched_policy": "",
                        "denial_reason": "",
                        "denied_by": "",
                    }
                ),
            ) as mock_eval,
        ):
            await authorize(db, evaluator, request)

        assert mock_eval.await_args is not None
        authz_input = mock_eval.await_args.args[1]
        assert authz_input["resource"]["any_project"] is False
