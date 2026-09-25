"""Unit tests for form_prompt activity."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from temporalio.activity import _CompleteAsyncError as CompleteAsyncError

from syntara.workflows.workflow_engine.activities.form_prompt_activity import (
    FormPromptActivityError,
    cancel_form_prompts_activity,
    create_form_prompt_activity,
    expire_form_prompts_activity,
    fail_detached_form_prompt_activity,
)


@pytest.fixture(autouse=True)
def _mock_heartbeat() -> Generator[None, None, None]:
    """Mock temporalio.activity.heartbeat for all tests."""
    with patch("syntara.workflows.workflow_engine.activities.form_prompt_activity.activity.heartbeat"):
        yield


class TestCreateFormPromptActivity:
    """Tests for create_form_prompt_activity."""

    async def test_creates_prompt_and_raises_complete_async(self):
        """Activity creates form prompt and raises CompleteAsyncError (AC-1)."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.create_form_prompt = AsyncMock()

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
                return_value=mock_client,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            await create_form_prompt_activity(
                execution_id=str(uuid4()),
                prompt_node_id="form1",
                name="Test Form",
                form_definition={"fields": []},
                project_id=str(uuid4()),
            )

        mock_client.create_form_prompt.assert_called_once()

    async def test_heartbeat_stops_activity_monitor(self):
        """Heartbeat sent with HEARTBEAT_STOP_MONITOR before HTTP call."""
        mock_heartbeat = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.create_form_prompt = AsyncMock()

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.form_prompt_activity.activity.heartbeat",
                mock_heartbeat,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
                return_value=mock_client,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            await create_form_prompt_activity(
                execution_id=str(uuid4()),
                prompt_node_id="form1",
                name="Test",
                form_definition={},
                project_id=str(uuid4()),
            )

        assert mock_heartbeat.called
        heartbeat_arg = mock_heartbeat.call_args[0][0]
        assert heartbeat_arg.get("stop_monitor") is True

    async def test_missing_project_id_raises_config_error(self):
        """Activity raises non-retryable ApplicationError when project_id is empty."""
        from temporalio.exceptions import ApplicationError

        with pytest.raises(ApplicationError) as exc_info:
            await create_form_prompt_activity(
                execution_id=str(uuid4()),
                prompt_node_id="form1",
                name="Test",
                form_definition={},
                project_id="",  # Empty!
            )

        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable

    async def test_client_error_wrapped_in_form_prompt_activity_error(self):
        """FormPromptsApiClientError is wrapped in FormPromptActivityError."""
        from syntara.workflows.clients.form_prompts_client import FormPromptsApiClientError

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.create_form_prompt = AsyncMock(side_effect=FormPromptsApiClientError("API error"))

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
                return_value=mock_client,
            ),
            pytest.raises(FormPromptActivityError) as exc_info,
        ):
            await create_form_prompt_activity(
                execution_id=str(uuid4()),
                prompt_node_id="form1",
                name="Test",
                form_definition={},
                project_id=str(uuid4()),
            )

        assert "API error" in str(exc_info.value)

    async def test_unexpected_exception_wrapped(self):
        """Unexpected exceptions are wrapped in FormPromptActivityError."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.create_form_prompt = AsyncMock(side_effect=RuntimeError("Unexpected"))

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
                return_value=mock_client,
            ),
            pytest.raises(FormPromptActivityError) as exc_info,
        ):
            await create_form_prompt_activity(
                execution_id=str(uuid4()),
                prompt_node_id="form1",
                name="Test",
                form_definition={},
                project_id=str(uuid4()),
            )

        assert "Unexpected error" in str(exc_info.value)

    async def test_request_payload_contains_all_fields(self):
        """All positional args are included in the request payload."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.create_form_prompt = AsyncMock()

        exec_id = str(uuid4())
        proj_id = str(uuid4())

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
                return_value=mock_client,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            await create_form_prompt_activity(
                execution_id=exec_id,
                prompt_node_id="form1",
                name="Test Form",
                form_definition={"fields": []},
                timeout_at="2024-01-01T00:00:00Z",
                responder_user_ids=[str(uuid4())],
                responder_group_ids=[str(uuid4())],
                project_id=proj_id,
                loop_iteration_path=[0, 1],
                temporal_activity_id="form1_iter_0_iter_1",
                message="Please fill this out",
                submit_label="Submit",
                success_message="Done!",
                timezone="UTC",
                css_override=".form { color: red; }",
            )

        call_args = mock_client.create_form_prompt.call_args[0][0]
        assert call_args["execution_id"] == exec_id
        assert call_args["project_id"] == proj_id
        assert call_args["prompt_node_id"] == "form1"
        assert call_args["name"] == "Test Form"
        assert call_args["form_definition"] == {"fields": []}
        assert call_args["loop_iteration_path"] == [0, 1]
        assert call_args["temporal_activity_id"] == "form1_iter_0_iter_1"
        assert call_args["message"] == "Please fill this out"
        assert call_args["submit_label"] == "Submit"
        assert call_args["success_message"] == "Done!"
        assert call_args["timezone"] == "UTC"
        assert call_args["css_override"] == ".form { color: red; }"


class TestExpireFormPromptsActivity:
    """Tests for expire_form_prompts_activity (AC-5)."""

    async def test_expires_all_pending_for_execution(self):
        """Expires all pending form prompts for an execution."""
        exec_id = str(uuid4())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.list_form_prompts_by_execution = AsyncMock(
            return_value=[
                {"id": str(uuid4()), "prompt_node_id": "form1"},
                {"id": str(uuid4()), "prompt_node_id": "form2"},
            ]
        )
        mock_client.batch_expire = AsyncMock(return_value={"total_success": 2, "total_failed": 0})

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
            return_value=mock_client,
        ):
            result = await expire_form_prompts_activity(exec_id)

        assert result["expired_count"] == 2
        mock_client.batch_expire.assert_called_once()

    async def test_node_id_filters_to_matching_loop_iteration(self):
        """When node_id is given, only matching loop iteration is expired."""
        exec_id = str(uuid4())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.list_form_prompts_by_execution = AsyncMock(
            return_value=[
                {"id": str(uuid4()), "prompt_node_id": "form1"},
                {"id": str(uuid4()), "prompt_node_id": "form1_iter_0"},
                {"id": str(uuid4()), "prompt_node_id": "form2"},
            ]
        )
        mock_client.batch_expire = AsyncMock(return_value={"total_success": 2, "total_failed": 0})

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
            return_value=mock_client,
        ):
            await expire_form_prompts_activity(exec_id, node_id="form1")

        # Should match "form1" and "form1_iter_0" but not "form2"
        call_args = mock_client.batch_expire.call_args[0][0]
        assert len(call_args) == 2

    async def test_no_pending_prompts_is_noop(self):
        """Returns zero count when no pending prompts exist."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.list_form_prompts_by_execution = AsyncMock(return_value=[])

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
            return_value=mock_client,
        ):
            result = await expire_form_prompts_activity(str(uuid4()))

        assert result["expired_count"] == 0
        mock_client.batch_expire.assert_not_called()

    async def test_records_snapshotted_before_batch_call(self):
        """Records are captured before the mutating call (for future audit events)."""
        exec_id = str(uuid4())
        prompt_id = str(uuid4())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.list_form_prompts_by_execution = AsyncMock(
            return_value=[{"id": prompt_id, "prompt_node_id": "form1"}]
        )

        # Make batch_expire raise to verify records were built before the call
        mock_client.batch_expire = AsyncMock(side_effect=Exception("Batch failed"))

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
            return_value=mock_client,
        ):
            result = await expire_form_prompts_activity(exec_id)

        # Should fail gracefully, but records were already built
        assert result["expired_count"] == 0
        assert "error" in result


class TestCancelFormPromptsActivity:
    """Tests for cancel_form_prompts_activity."""

    async def test_cancels_all_pending_for_execution(self):
        """Cancels all pending form prompts for an execution."""
        exec_id = str(uuid4())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.list_form_prompts_by_execution = AsyncMock(
            return_value=[{"id": str(uuid4()), "prompt_node_id": "form1"}]
        )
        mock_client.batch_cancel = AsyncMock(return_value={"total_success": 1, "total_failed": 0})

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
            return_value=mock_client,
        ):
            result = await cancel_form_prompts_activity(exec_id)

        assert result["cancelled_count"] == 1

    async def test_no_pending_prompts_is_noop(self):
        """Returns zero count when no pending prompts exist."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.list_form_prompts_by_execution = AsyncMock(return_value=[])

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.FormPromptsApiClient",
            return_value=mock_client,
        ):
            result = await cancel_form_prompts_activity(str(uuid4()))

        assert result["cancelled_count"] == 0


class TestFailDetachedFormPromptActivity:
    """Tests for fail_detached_form_prompt_activity."""

    async def test_fails_async_activity_handle(self):
        """Activity calls handle.fail() with the detached error."""
        mock_handle = AsyncMock()
        mock_temporal_client = MagicMock()
        mock_temporal_client.get_async_activity_handle = MagicMock(return_value=mock_handle)
        mock_sync_service = MagicMock()
        mock_sync_service.temporal_client = mock_temporal_client

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.get_activity_sync_service",
            return_value=mock_sync_service,
        ):
            await fail_detached_form_prompt_activity("wf_id", "run_id", "form1_iter_0")

        mock_handle.fail.assert_called_once()

    async def test_swallows_not_found_rpc_error(self):
        """Swallows RPCError containing 'not found'."""
        from temporalio.service import RPCError, RPCStatusCode

        mock_temporal_client = MagicMock()
        mock_temporal_client.get_async_activity_handle = MagicMock(
            side_effect=RPCError("Activity not found", RPCStatusCode.NOT_FOUND, b"")
        )
        mock_sync_service = MagicMock()
        mock_sync_service.temporal_client = mock_temporal_client

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.get_activity_sync_service",
            return_value=mock_sync_service,
        ):
            # Should not raise
            await fail_detached_form_prompt_activity("wf_id", "run_id", "form1")

    async def test_swallows_already_completed_rpc_error(self):
        """Swallows RPCError containing 'already completed'."""
        from temporalio.service import RPCError, RPCStatusCode

        mock_handle = AsyncMock()
        mock_handle.fail = AsyncMock(
            side_effect=RPCError("Activity already completed", RPCStatusCode.FAILED_PRECONDITION, b"")
        )
        mock_temporal_client = MagicMock()
        mock_temporal_client.get_async_activity_handle = MagicMock(return_value=mock_handle)
        mock_sync_service = MagicMock()
        mock_sync_service.temporal_client = mock_temporal_client

        with patch(
            "syntara.workflows.workflow_engine.activities.form_prompt_activity.get_activity_sync_service",
            return_value=mock_sync_service,
        ):
            # Should not raise
            await fail_detached_form_prompt_activity("wf_id", "run_id", "form1")

    async def test_reraises_unexpected_rpc_error(self):
        """Reraises RPCError that doesn't match known phrases."""
        from temporalio.service import RPCError, RPCStatusCode

        mock_handle = AsyncMock()
        mock_handle.fail = AsyncMock(side_effect=RPCError("Server error", RPCStatusCode.UNKNOWN, b""))
        mock_temporal_client = MagicMock()
        mock_temporal_client.get_async_activity_handle = MagicMock(return_value=mock_handle)
        mock_sync_service = MagicMock()
        mock_sync_service.temporal_client = mock_temporal_client

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.form_prompt_activity.get_activity_sync_service",
                return_value=mock_sync_service,
            ),
            pytest.raises(RPCError),
        ):
            await fail_detached_form_prompt_activity("wf_id", "run_id", "form1")
