"""AUDIT-2: Service identity authorization — OPA bypass verification.

Validates that mTLS-authenticated (cert-based) service requests bypass
OPA authorization checks.  Per the current architecture, service principals
receive implicit full access — ``PermissionChecker``, ``ProjectScopeFilter``,
and ``VisibilityFilter`` all short-circuit when ``request.state.is_cert_authenticated``
is ``True``. ``WorkflowService`` also bypasses its per-credential ``use`` check
when constructed with ``is_cert_authenticated=True``.

These tests verify the bypass logic remains intact so that inter-service
communication is never blocked by user-level RBAC policies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.dependencies import PermissionChecker, ProjectScopeFilter, VisibilityFilter
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.workflows.services.workflow_service import WorkflowService

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _seed_authenticated_group() -> None:
    """Override database seeding for these mocked authorization component tests."""


def _make_cert_request() -> MagicMock:
    """Create a mock request with cert-authenticated state."""
    request = MagicMock()
    request.state.is_cert_authenticated = True
    request.state.cert_cn = "backend.ao.svc"
    return request


def _make_unauthenticated_request() -> MagicMock:
    """Create a mock request without cert authentication."""
    request = MagicMock()
    request.state.is_cert_authenticated = False
    request.state.cert_cn = None
    return request


class TestAUDIT2PermissionCheckerBypass:
    """PermissionChecker short-circuits for cert-authenticated requests."""

    @pytest.mark.asyncio
    async def test_cert_auth_skips_opa(self) -> None:
        checker = PermissionChecker(resource_type="workflow", action="read")
        request = _make_cert_request()
        mock_user = MagicMock()
        mock_db = AsyncMock()

        with patch("syntara.authz.dependencies.get_authz_evaluator") as mock_evaluator:
            await checker(request=request, current_user=mock_user, db=mock_db)

        mock_evaluator.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_cert_calls_opa(self) -> None:
        """Control: non-cert requests DO call OPA."""
        checker = PermissionChecker(resource_type="workflow", action="read")
        request = _make_unauthenticated_request()
        mock_user = MagicMock()
        mock_db = AsyncMock()

        with (
            patch("syntara.authz.dependencies.get_authz_evaluator") as mock_evaluator,
            patch("syntara.authz.dependencies.authorize", new_callable=AsyncMock) as mock_authorize,
        ):
            mock_authorize.return_value = MagicMock(allowed=True)
            await checker(request=request, current_user=mock_user, db=mock_db)

        mock_evaluator.assert_called_once()


class TestAUDIT2ProjectScopeFilterBypass:
    """ProjectScopeFilter returns all_projects=True for cert-authenticated requests."""

    @pytest.mark.asyncio
    async def test_cert_auth_returns_all_projects(self) -> None:
        scope_filter = ProjectScopeFilter(resource_type="workflow", action="read")
        request = _make_cert_request()
        mock_user = MagicMock()
        mock_db = AsyncMock()

        with patch("syntara.authz.dependencies.get_authz_evaluator") as mock_evaluator:
            result = await scope_filter(request=request, current_user=mock_user, db=mock_db)

        mock_evaluator.assert_not_called()
        assert result.all_projects is True


class TestAUDIT2VisibilityFilterBypass:
    """VisibilityFilter returns unrestricted=True for cert-authenticated requests."""

    @pytest.mark.asyncio
    async def test_cert_auth_returns_unrestricted(self) -> None:
        vis_filter = VisibilityFilter(resource_type="workflow", action="read")
        request = _make_cert_request()
        mock_user = MagicMock()
        mock_db = AsyncMock()

        with patch("syntara.authz.dependencies.get_authz_evaluator") as mock_evaluator:
            result = await vis_filter(request=request, current_user=mock_user, db=mock_db)

        mock_evaluator.assert_not_called()
        assert result.unrestricted is True


class TestAUDIT2WorkflowServiceBypass:
    """WorkflowService honors the same certificate-only authorization bypass."""

    async def test_cert_auth_skips_credential_use_check(self) -> None:
        """A normally constructed certificate caller needs no OPA client or lookup."""
        session = AsyncMock()
        service = WorkflowService(session, MagicMock(), is_cert_authenticated=True)
        with patch("syntara.workflows.services.workflow_service.authorize") as authorize:
            await service._check_credential_use_permission(
                {str(uuid4())}, previous_credential_ids=None, project_id=uuid4()
            )
        authorize.assert_not_called()
        session.exec.assert_not_called()

    async def test_non_cert_still_checks_credential_use(self) -> None:
        """An ordinary caller is denied when OPA denies the selected credential."""
        session = AsyncMock()
        project = MagicMock()
        project.first.return_value = "destination"
        session.exec.return_value = project
        user = MagicMock(id=uuid4(), labels={}, authz_metadata={})
        service = WorkflowService(session, user, MagicMock())
        credential_id = str(uuid4())
        with (
            patch(
                "syntara.workflows.services.workflow_service.authorize",
                new_callable=AsyncMock,
                return_value=MagicMock(allowed=False),
            ) as authorize,
            pytest.raises(AuthorizationDeniedError),
        ):
            await service._check_credential_use_permission(
                {credential_id}, previous_credential_ids=None, project_id=uuid4()
            )
        authorize.assert_awaited_once()
        request = authorize.call_args.args[2]
        assert request.resource_type == "credential"
        assert request.resource_id == credential_id
        assert request.action == "use"
