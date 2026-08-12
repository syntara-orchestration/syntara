"""Integration tests for GET /api/v1/files/storage_status."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

_ENDPOINT = "/api/v1/files/storage_status"


class TestFileStorageStatusEndpoint:
    """Object storage availability is reported here, not on the readiness probe."""

    @pytest.mark.asyncio
    async def test_reports_ok_when_storage_is_reachable(self, auth_client: AsyncClient) -> None:
        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_retriever = MagicMock()
        mock_retriever.health_check = AsyncMock(return_value=True)
        mock_fm.get_retriever.return_value = mock_retriever

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            resp = await auth_client.get(_ENDPOINT)

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_reports_unconfigured_when_s3_is_not_set_up(self, auth_client: AsyncClient) -> None:
        """The frontend's useFileStorageStatus hook gates upload controls on this."""
        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=False)

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            resp = await auth_client.get(_ENDPOINT)

        assert resp.status_code == 200
        assert resp.json()["status"] == "unconfigured"

    @pytest.mark.asyncio
    async def test_reports_degraded_when_probe_fails(self, auth_client: AsyncClient) -> None:
        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_retriever = MagicMock()
        mock_retriever.health_check = AsyncMock(return_value=False)
        mock_fm.get_retriever.return_value = mock_retriever

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            resp = await auth_client.get(_ENDPOINT)

        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_reports_error_and_never_raises(self, auth_client: AsyncClient) -> None:
        """A broken object store is reported as a status, not a 5xx."""
        with patch("syntara.files.health.get_file_manager", side_effect=RuntimeError("S3 is down")):
            resp = await auth_client.get(_ENDPOINT)

        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    @pytest.mark.asyncio
    async def test_requires_authentication(self, base_client: AsyncClient) -> None:
        """Deployment configuration state is not public."""
        resp = await base_client.get(_ENDPOINT)

        assert resp.status_code == 401
