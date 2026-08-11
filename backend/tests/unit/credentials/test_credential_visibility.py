"""Unit tests for _CredentialVisibility — cert, for_action=use, and default paths."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.engine import VisibilityResult
from syntara.credentials.router import _CredentialVisibility


def _make_request(*, cert_auth: bool = False, for_action: str | None = None) -> MagicMock:
    request = MagicMock()
    request.state.is_cert_authenticated = cert_auth
    request.query_params.get.side_effect = lambda key, default=None: for_action if key == "for_action" else default
    return request


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.labels = {"team": "test"}
    user.authz_metadata = {"org": "acme"}
    return user


class TestCredentialVisibilityCertAuth:  # noqa: D101
    @pytest.mark.asyncio
    async def test_cert_authenticated_returns_unrestricted(self) -> None:
        """S2S cert-authenticated requests bypass OPA entirely."""
        visibility = _CredentialVisibility()
        result = await visibility(
            request=_make_request(cert_auth=True),
            current_user=_make_user(),
            db=AsyncMock(),
            evaluator=MagicMock(),
        )
        assert result.unrestricted is True
        assert isinstance(result, VisibilityResult)


class TestCredentialVisibilityForActionUse:  # noqa: D101
    @pytest.mark.asyncio
    async def test_for_action_use_calls_credential_use_visibility(self) -> None:
        """for_action=use dispatches to resolve_credential_use_visibility."""
        visibility = _CredentialVisibility()
        user = _make_user()
        db = AsyncMock()
        evaluator = MagicMock()
        expected = VisibilityResult(unrestricted=False, allowed_project_ids=[uuid4()])

        with patch("syntara.credentials.router.resolve_credential_use_visibility", return_value=expected) as mock_use:
            result = await visibility(
                request=_make_request(for_action="use"),
                current_user=user,
                db=db,
                evaluator=evaluator,
            )

        mock_use.assert_called_once_with(
            db=db,
            evaluator=evaluator,
            user_id=user.id,
            user_labels=user.labels,
            user_metadata=user.authz_metadata,
        )
        assert result is expected


class TestCredentialVisibilityDefault:  # noqa: D101
    @pytest.mark.asyncio
    async def test_default_calls_resolve_visibility(self) -> None:
        """No for_action dispatches to resolve_visibility for credential:read."""
        visibility = _CredentialVisibility()
        user = _make_user()
        db = AsyncMock()
        evaluator = MagicMock()
        expected = VisibilityResult(unrestricted=True)

        with patch("syntara.credentials.router.resolve_visibility", return_value=expected) as mock_vis:
            result = await visibility(
                request=_make_request(),
                current_user=user,
                db=db,
                evaluator=evaluator,
            )

        mock_vis.assert_called_once_with(
            db=db,
            evaluator=evaluator,
            user_id=user.id,
            resource_type="credential",
            action="read",
            user_labels=user.labels,
            user_metadata=user.authz_metadata,
        )
        assert result is expected
