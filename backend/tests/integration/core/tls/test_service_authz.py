"""AUDIT-2: Service identity authorization — OPA bypass verification.

Validates that mTLS-authenticated (cert-based) service requests bypass
OPA authorization checks.  Per the current architecture, service principals
receive implicit full access — ``PermissionChecker``, ``ProjectScopeFilter``,
and ``VisibilityFilter`` all short-circuit when ``request.state.is_cert_authenticated``
is ``True``.

These tests verify the bypass logic remains intact so that inter-service
communication is never blocked by user-level RBAC policies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.authz.dependencies import PermissionChecker, ProjectScopeFilter, VisibilityFilter

pytestmark = [pytest.mark.integration]


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
