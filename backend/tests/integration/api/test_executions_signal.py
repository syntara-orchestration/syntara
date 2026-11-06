"""Integration tests for workflow execution activity signal endpoint."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.core.models import User
from syntara.forms.models.api_models import FormPromptStatus
from syntara.forms.models.form_prompt import FormPrompt
from syntara.workflows.exceptions import ExecutionNotFoundError, TemporalUnavailableError
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.models.execution import Execution


async def _create_signal_form_prompt(
    session: AsyncSession,
    execution: Execution,
    *,
    temporal_activity_id: str,
    prompt_node_id: str,
    prompt_status: FormPromptStatus,
    response_data: dict[str, Any] | None = None,
    responded_by: uuid.UUID | None = None,
) -> FormPrompt:
    """Persist a prompt row for signal callback tests."""
    prompt = FormPrompt(
        execution_id=execution.id,
        project_id=execution.project_id,
        prompt_node_id=prompt_node_id,
        loop_iteration_path=[0] if "_iter_" in temporal_activity_id else [],
        temporal_activity_id=temporal_activity_id,
        name="Signal test form",
        form_definition={"fields": [{"value_name": "reason", "type": "text", "label": "Reason", "required": True}]},
        status=prompt_status,
        response_data=response_data,
        responded_by=responded_by,
        responded_at=datetime.now(UTC) if prompt_status == FormPromptStatus.SUBMITTED else None,
    )
    session.add(prompt)
    await session.commit()
    return prompt


def _execution_read_with_node(
    execution: Execution,
    *,
    node_id: str,
    node_type: str,
) -> SimpleNamespace:
    """Build the workflow metadata needed to classify a callback target."""
    return SimpleNamespace(
        temporal_workflow_id=execution.temporal_workflow_id,
        workflow_definition=SimpleNamespace(
            triggers=[],
            nodes=[{"id": node_id, "type": node_type}],
        ),
    )


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


@pytest.mark.asyncio
class TestFormPromptSignalVerification:
    """Integration coverage for Form Prompt callback reconciliation."""

    @staticmethod
    def _mock_temporal(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
        temporal = AsyncMock()
        monkeypatch.setitem(
            app.dependency_overrides,
            cast("Any", get_temporal_execution_service),
            cast("Any", lambda: temporal),
        )
        return temporal

    async def test_known_form_prompt_without_row_is_rejected(
        self,
        auth_client: AsyncClient,
        test_execution: Execution,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        temporal = self._mock_temporal(monkeypatch)
        activity_id = "form-node_iter_0"

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.get_execution",
            new_callable=AsyncMock,
            return_value=_execution_read_with_node(test_execution, node_id="form-node", node_type="form_prompt"),
        ):
            response = await auth_client.post(
                f"/api/v1/executions/{test_execution.id}/activities/{activity_id}/signal",
                json={"signal_data": {"outcome": "submitted", "response_data": {"reason": "forged"}}},
            )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "FORM_PROMPT_SUBMISSION_REQUIRED"
        temporal.complete_async_activity.assert_not_awaited()
        temporal.fail_async_activity.assert_not_awaited()

    async def test_pending_prompt_rejects_forged_completion(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_execution: Execution,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        temporal = self._mock_temporal(monkeypatch)
        activity_id = "form-node"
        prompt = await _create_signal_form_prompt(
            test_db_session,
            test_execution,
            temporal_activity_id=activity_id,
            prompt_node_id=activity_id,
            prompt_status=FormPromptStatus.PENDING,
        )

        response = await auth_client.post(
            f"/api/v1/executions/{test_execution.id}/activities/{activity_id}/signal",
            json={"signal_data": {"outcome": "submitted", "response_data": {"reason": "forged"}}},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "FORM_PROMPT_SUBMISSION_REQUIRED"
        assert str(prompt.id) not in response.json()["detail"]
        assert prompt.status == FormPromptStatus.PENDING
        temporal.complete_async_activity.assert_not_awaited()
        temporal.fail_async_activity.assert_not_awaited()

    @pytest.mark.parametrize("prompt_status", [FormPromptStatus.EXPIRED, FormPromptStatus.CANCELLED])
    async def test_terminal_unsubmitted_prompt_rejects_completion(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_execution: Execution,
        monkeypatch: pytest.MonkeyPatch,
        prompt_status: FormPromptStatus,
    ) -> None:
        temporal = self._mock_temporal(monkeypatch)
        activity_id = f"form-{prompt_status.value}"
        await _create_signal_form_prompt(
            test_db_session,
            test_execution,
            temporal_activity_id=activity_id,
            prompt_node_id=activity_id,
            prompt_status=prompt_status,
        )

        response = await auth_client.post(
            f"/api/v1/executions/{test_execution.id}/activities/{activity_id}/signal",
            json={"signal_data": {"outcome": "submitted", "response_data": {"reason": "forged"}}},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        temporal.complete_async_activity.assert_not_awaited()

    async def test_submitted_loop_prompt_uses_persisted_payload_without_activity_row(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_execution: Execution,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Loop IDs like ``form-node_iter_0`` use saved form data, not data from the signal."""
        temporal = self._mock_temporal(monkeypatch)
        activity_id = "form-node_iter_0"
        response_data = {"reason": "validated persisted response"}
        prompt = await _create_signal_form_prompt(
            test_db_session,
            test_execution,
            temporal_activity_id=activity_id,
            prompt_node_id="form-node",
            prompt_status=FormPromptStatus.SUBMITTED,
            response_data=response_data,
            responded_by=test_user.id,
        )

        with patch(
            "syntara.workflows.services.execution_service.ExecutionService.get_execution",
            new_callable=AsyncMock,
            return_value=_execution_read_with_node(test_execution, node_id="form-node", node_type="form_prompt"),
        ):
            response = await auth_client.post(
                f"/api/v1/executions/{test_execution.id}/activities/{activity_id}/signal",
                json={"signal_data": {"outcome": "submitted", "response_data": {"reason": "forged"}}},
            )

        assert response.status_code == status.HTTP_200_OK
        temporal.complete_async_activity.assert_awaited_once()
        assert prompt.responded_at is not None
        responded_at = prompt.responded_at.isoformat()
        assert temporal.complete_async_activity.await_args.kwargs["result"] == {
            "output": {
                "outcome": "submitted",
                "response_data": response_data,
                "responded_by": test_user.username,
                "responded_at": responded_at,
                "prompt_id": str(prompt.id),
            }
        }

    @pytest.mark.parametrize("signal_status", ["failed", "cancelled"])
    async def test_form_prompt_rejects_forged_failure_and_cancellation(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_execution: Execution,
        monkeypatch: pytest.MonkeyPatch,
        signal_status: str,
    ) -> None:
        temporal = self._mock_temporal(monkeypatch)
        activity_id = f"form-{signal_status}"
        await _create_signal_form_prompt(
            test_db_session,
            test_execution,
            temporal_activity_id=activity_id,
            prompt_node_id=activity_id,
            prompt_status=FormPromptStatus.PENDING,
        )

        response = await auth_client.post(
            f"/api/v1/executions/{test_execution.id}/activities/{activity_id}/signal",
            json={"signal_data": {"status": signal_status}},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        temporal.complete_async_activity.assert_not_awaited()
        temporal.fail_async_activity.assert_not_awaited()

    async def test_known_non_form_activity_keeps_generic_completion(
        self,
        auth_client: AsyncClient,
        test_execution: Execution,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Known non-form nodes skip the Forms lookup; the agentic E2E is race-prone."""
        temporal = self._mock_temporal(monkeypatch)
        signal_data = {"status": "completed", "result": {"value": "script"}}

        with patch(
            "syntara.workflows.services.activity_callback.resolve_verified_form_prompt_signal",
            new_callable=AsyncMock,
        ) as mock_resolver:
            response = await auth_client.post(
                f"/api/v1/executions/{test_execution.id}/activities/test_activity/signal",
                json={"signal_data": signal_data},
            )

        assert response.status_code == status.HTTP_200_OK
        temporal.complete_async_activity.assert_awaited_once()
        assert temporal.complete_async_activity.await_args.kwargs["result"] == {"output": signal_data}
        mock_resolver.assert_not_awaited()
