"""Integration tests for workflow execution activity signal endpoint."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient

from syntara.workflows.exceptions import ExecutionNotFoundError, TemporalUnavailableError


@pytest.mark.asyncio
class TestSignalActivity:
    """Integration tests for POST /executions/{execution_id}/activities/{activity_id}/signal."""

    async def test_signal_activity_with_valid_payload(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test sending signal to activity with valid ActivitySignalPayload."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "test_activity"
        payload = {
            "signal_data": {
                "status": "completed",
                "result": {"content": "Test result"},
            }
        }

        # Mock the service method
        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.handle_activity_callback",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            # Act
            response = await auth_client.post(
                f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
                json=payload,
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "signal_sent"
            assert data["message"] == f"Signal sent to activity {activity_id}"

            # Verify service was called correctly
            mock_send.assert_called_once_with(
                execution_id=execution_id,
                activity_id=activity_id,
                signal_data=payload["signal_data"],
            )

    async def test_signal_activity_with_nested_signal_data(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test sending signal with nested signal_data structure."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "agentic_task"
        payload = {
            "signal_data": {
                "id": "inv-123",
                "status": "completed",
                "result": {
                    "content": "Analysis complete",
                    "response_metadata": {
                        "model": "claude-3.5-sonnet",
                        "tokens": 150,
                    },
                },
                "timestamp": "2026-01-14T12:00:00Z",
                "agent_type": "GenericAgent",
            }
        }

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.handle_activity_callback",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # Act
            response = await auth_client.post(
                f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
                json=payload,
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK

    async def test_signal_activity_with_error_signal_data(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test sending error signal with failure status."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "failing_task"
        payload = {
            "signal_data": {
                "status": "failed",
                "error": {
                    "message": "Execution failed",
                    "error_type": "AgentError",
                },
                "timestamp": "2026-01-14T12:00:00Z",
            }
        }

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.handle_activity_callback",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # Act
            response = await auth_client.post(
                f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
                json=payload,
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK

    async def test_signal_activity_with_empty_signal_data(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test sending signal with empty signal_data."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "test_activity"
        payload: dict[str, dict[str, str]] = {"signal_data": {}}

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.handle_activity_callback",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # Act
            response = await auth_client.post(
                f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
                json=payload,
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK

    async def test_signal_activity_missing_signal_data_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that missing signal_data returns 422 validation error."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "test_activity"
        payload: dict[str, str] = {}  # Missing required signal_data field

        # Act
        response = await auth_client.post(
            f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
            json=payload,
        )

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert "detail" in data
        # Validation error should mention signal_data
        assert "signal_data" in data["detail"]

    async def test_signal_activity_invalid_signal_data_type_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that invalid signal_data type returns 422."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "test_activity"
        payload = {"signal_data": "not a dict"}  # Should be dict, not string

        # Act
        response = await auth_client.post(
            f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
            json=payload,
        )

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_signal_activity_execution_not_found_returns_404(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that non-existent execution returns 404."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "test_activity"
        payload = {"signal_data": {"status": "completed"}}

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.handle_activity_callback",
            new_callable=AsyncMock,
            return_value=None,
            side_effect=ExecutionNotFoundError(execution_id),
        ):
            # Act
            response = await auth_client.post(
                f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
                json=payload,
            )

            # Assert
            assert response.status_code == status.HTTP_404_NOT_FOUND
            data = response.json()
            assert "not found" in data["detail"].lower()

    async def test_signal_activity_temporal_unavailable_returns_503(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that Temporal unavailability returns 503."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "test_activity"
        payload = {"signal_data": {"status": "completed"}}

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.handle_activity_callback",
            new_callable=AsyncMock,
            return_value=None,
            side_effect=TemporalUnavailableError("Temporal server unavailable"),
        ):
            # Act
            response = await auth_client.post(
                f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
                json=payload,
            )

            # Assert
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    async def test_signal_activity_response_structure(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that response matches SignalResponse schema."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "test_activity"
        payload = {"signal_data": {"status": "completed"}}

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.handle_activity_callback",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # Act
            response = await auth_client.post(
                f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
                json=payload,
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Verify SignalResponse structure
            assert "status" in data
            assert data["status"] == "signal_sent"
            assert "message" in data
            assert isinstance(data["message"], str)

    async def test_signal_activity_with_special_characters_in_activity_id(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test signal with activity_id containing special characters."""
        # Arrange
        execution_id = uuid.uuid4()
        activity_id = "task-with-dashes_and_underscores.123"
        payload = {"signal_data": {"status": "completed"}}

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.handle_activity_callback",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send:
            # Act
            response = await auth_client.post(
                f"/api/v1/executions/{execution_id}/activities/{activity_id}/signal",
                json=payload,
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK
            mock_send.assert_called_once_with(
                execution_id=execution_id,
                activity_id=activity_id,
                signal_data=payload["signal_data"],
            )
