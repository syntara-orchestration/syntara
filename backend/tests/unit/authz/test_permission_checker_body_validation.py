"""Unit tests for PermissionChecker body validation.

Verifies that ``_resolve_project_from_body`` rejects non-dict JSON
request bodies with a ``RequestValidationError``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.exceptions import RequestValidationError

from syntara.authz.dependencies import PermissionChecker


def _make_request(body_value: object) -> MagicMock:
    """Return a mock Request whose ``.json()`` resolves to *body_value*."""
    request = MagicMock()
    request.json = AsyncMock(return_value=body_value)
    return request


class TestResolveProjectFromBodyValidation:
    """Test that _resolve_project_from_body rejects non-dict bodies."""

    @pytest.fixture
    def checker(self) -> PermissionChecker:
        return PermissionChecker("role-assignment", "create", body_project_field="project_id")

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    # -- happy path ----------------------------------------------------------

    async def test_dict_body_accepted(self, checker: PermissionChecker, mock_db: AsyncMock) -> None:
        """A dict body with a missing project field returns empty string."""
        request = _make_request({"project_id": None})
        result = await checker._resolve_project_from_body(request, mock_db)
        assert result == ""

    # -- rejection cases ------------------------------------------------------

    async def test_null_body_rejected(self, checker: PermissionChecker, mock_db: AsyncMock) -> None:
        request = _make_request(None)
        with pytest.raises(RequestValidationError):
            await checker._resolve_project_from_body(request, mock_db)

    async def test_string_body_rejected(self, checker: PermissionChecker, mock_db: AsyncMock) -> None:
        request = _make_request("hello")
        with pytest.raises(RequestValidationError):
            await checker._resolve_project_from_body(request, mock_db)

    async def test_list_body_rejected(self, checker: PermissionChecker, mock_db: AsyncMock) -> None:
        request = _make_request([1, 2, 3])
        with pytest.raises(RequestValidationError):
            await checker._resolve_project_from_body(request, mock_db)

    async def test_number_body_rejected(self, checker: PermissionChecker, mock_db: AsyncMock) -> None:
        request = _make_request(42)
        with pytest.raises(RequestValidationError):
            await checker._resolve_project_from_body(request, mock_db)

    @pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
    async def test_bool_body_rejected(self, checker: PermissionChecker, mock_db: AsyncMock, value: object) -> None:
        request = _make_request(value)
        with pytest.raises(RequestValidationError):
            await checker._resolve_project_from_body(request, mock_db)
