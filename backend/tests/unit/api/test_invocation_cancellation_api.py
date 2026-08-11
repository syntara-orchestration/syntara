"""Unit tests for invocation cancellation API endpoint."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from syntara.agent_orchestrator.models import Invocation, InvocationStatus
from syntara.agent_orchestrator.models.request import (
    CancellationResult,
    InvocationCancelRequest,
)
from syntara.invocations.router import cancel_invocation


class TestInvocationCancellationAPI:
    """Test cancellation API endpoint business logic."""

    @pytest.mark.asyncio
    async def test_cancel_invocation_success(self) -> None:
        """Test successful invocation cancellation via API."""
        invocation_id = uuid4()
        request = InvocationCancelRequest(reason="Test cancellation")

        with patch("syntara.invocations.router.InvocationService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.cancel_invocation.return_value = CancellationResult.SUCCESS
            mock_service_class.return_value = mock_service

        response = await cancel_invocation(
            invocation_id=str(invocation_id),
            request_body=request,
            service=mock_service,
        )

        assert response.success is True
        mock_service.cancel_invocation.assert_called_once_with(invocation_id, "Test cancellation")

    @pytest.mark.asyncio
    async def test_cancel_invocation_not_found(self) -> None:
        """Test cancellation when invocation is not found."""
        invocation_id = uuid4()
        request = InvocationCancelRequest(reason="Test cancellation")

        with patch("syntara.invocations.router.InvocationService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.cancel_invocation.return_value = CancellationResult.NOT_FOUND
            mock_service_class.return_value = mock_service

        with pytest.raises(HTTPException) as exc_info:
            await cancel_invocation(
                invocation_id=str(invocation_id),
                request_body=request,
                service=mock_service,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_cancel_invocation_not_cancellable(self) -> None:
        """Test cancellation when invocation cannot be cancelled."""
        invocation_id = uuid4()
        request = InvocationCancelRequest(reason="Test cancellation")

        with patch("syntara.invocations.router.InvocationService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.cancel_invocation.return_value = CancellationResult.NOT_CANCELLABLE
            mock_service_class.return_value = mock_service

        # Mock get_invocation for the error case
        mock_invocation = Invocation(
            id=invocation_id,
            session_id="test",
            prompt="test",
            status=InvocationStatus.COMPLETED,
        )
        mock_service.get_invocation.return_value = mock_invocation

        with pytest.raises(HTTPException) as exc_info:
            await cancel_invocation(
                invocation_id=str(invocation_id),
                request_body=request,
                service=mock_service,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
