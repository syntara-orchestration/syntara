"""Tests for ScheduledTriggerService.

Covers:
- Sync scheduled triggers on publish (create, update, stale deletion)
- Delete all triggers for workflow (prefix scan)
- Graceful Temporal unavailability
- Non-scheduled triggers ignored
- Validation errors
- Search attribute registration and server-side filtering
"""

import asyncio
import gc
import weakref
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.api.enums.v1 import IndexedValueType
from temporalio.client import ScheduleAlreadyRunningError, ScheduleOverlapPolicy
from temporalio.common import TypedSearchAttributes
from temporalio.service import RPCError, RPCStatusCode

import syntara.workflows.services.scheduled_trigger_service as _mod
from syntara.workflows.exceptions import ScheduledTriggerSyncError, TriggerValidationError
from syntara.workflows.services.scheduled_trigger_service import (
    ScheduledTriggerService,
)


@pytest.fixture(autouse=True)
def _reset_module_caches() -> Generator[None]:
    """Reset module-level caches between tests."""

    def _clear() -> None:
        for task in {_mod._connect_task, *_mod._pending_connect_tasks}:
            if task is not None and not task.done():
                task.cancel()
        _mod._pending_connect_tasks.clear()
        _mod._search_attr_available = None
        _mod._cached_client = None
        _mod._connect_task = None
        _mod._connect_started_at = None

    _clear()
    yield
    _clear()


def _make_workflow_definition(
    triggers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal workflow definition with trigger nodes."""
    return {
        "schema_version": "2.0.0",
        "name": "test-workflow",
        "triggers": triggers or [],
        "nodes": [],
        "edges": [],
    }


def _make_scheduled_trigger(
    node_id: str = "trigger_1",
    schedule_type: str = "cron",
    cron: str = "0 9 * * *",
    **kwargs: str | None,
) -> dict[str, Any]:
    """Build a scheduled trigger node."""
    config: dict[str, str | None] = {"schedule_type": schedule_type}
    if schedule_type == "cron":
        config["cron"] = cron
    if schedule_type == "interval":
        config["interval"] = kwargs.get("interval", "R/2024-01-01T00:00:00Z/P1D")
    config.update(kwargs)
    return {
        "id": node_id,
        "type": "scheduled_trigger",
        "parameters": config,
    }


def _make_schedule_list_entry(schedule_id: str) -> MagicMock:
    """Create a mock schedule list entry with a given ID."""
    entry = MagicMock()
    entry.id = schedule_id
    return entry


async def _async_iter_from(items: list[Any]) -> AsyncIterator[Any]:
    """Create an async iterator from a list."""
    for item in items:
        yield item


def _make_mock_operator_service(
    *,
    attr_registered: bool = False,
    add_raises: RPCError | None = None,
    list_raises: RPCError | None = None,
) -> MagicMock:
    """Create a mock Temporal operator service."""
    operator = MagicMock()
    list_resp = MagicMock()
    if attr_registered:
        list_resp.custom_attributes = {
            "OrchestratorWorkflowId": IndexedValueType.INDEXED_VALUE_TYPE_KEYWORD,
        }
    else:
        list_resp.custom_attributes = {}

    if list_raises:
        operator.list_search_attributes = AsyncMock(side_effect=list_raises)
    else:
        operator.list_search_attributes = AsyncMock(return_value=list_resp)

    if add_raises:
        operator.add_search_attributes = AsyncMock(side_effect=add_raises)
    else:
        operator.add_search_attributes = AsyncMock()

    return operator


def _make_mock_client(
    *,
    search_attr_available: bool = True,
    list_raises: RPCError | None = None,
) -> MagicMock:
    """Create a mock Temporal client with schedule handle methods."""
    client = MagicMock()

    # Mock schedule handle
    handle = AsyncMock()
    handle.delete = AsyncMock()
    handle.update = AsyncMock()

    client.get_schedule_handle = MagicMock(return_value=handle)
    client.create_schedule = AsyncMock()
    client.list_schedules = AsyncMock(return_value=_async_iter_from([]))

    # Mock operator service for search attribute registration
    client.operator_service = _make_mock_operator_service(
        attr_registered=search_attr_available,
        list_raises=list_raises,
    )

    return client


class TestSyncScheduledTriggers:
    """Tests for sync_scheduled_triggers method."""

    async def test_sync_creates_new_schedule(self) -> None:
        """Should create a Temporal Schedule for new scheduled trigger nodes."""
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        count = await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        assert count == 1
        client.create_schedule.assert_called_once()
        # Verify the schedule ID convention
        call_args = client.create_schedule.call_args
        assert call_args[0][0] == "orchestrator-sched-wf-123-trigger_1"

    async def test_schedule_action_targets_launcher_workflow(self) -> None:
        """The schedule action must target 'scheduled_workflow_launcher'.

        This is the critical coupling: the overlap policy applies to this
        workflow. If the action target changes, the overlap policy breaks.
        """
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        schedule = client.create_schedule.call_args[0][1]
        assert schedule.action.workflow == "scheduled_workflow_launcher"

    async def test_sync_defaults_to_general_task_queue(self) -> None:
        """Regression guard for the task-queue routing fix below.

        Default (is_builtin not passed) must stay on the general task queue —
        this is the existing behaviour for user-authored workflows and must
        not change as a side effect of the fix.
        """
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        schedule = client.create_schedule.call_args[0][1]
        assert schedule.action.task_queue == "orchestrator-workflow-queue"

    async def test_sync_builtin_routes_to_background_task_queue(self) -> None:
        """Builtin workflows route to background task queue, not general queue."""
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
            is_builtin=True,
        )

        schedule = client.create_schedule.call_args[0][1]
        assert schedule.action.task_queue == "orchestrator-background-queue"

    async def test_sync_updates_existing_schedule(self) -> None:
        """Should update an existing Temporal Schedule when trigger config changes."""
        client = _make_mock_client()
        # Simulate existing schedule by making create raise ALREADY_EXISTS
        client.create_schedule = AsyncMock(side_effect=RPCError("already exists", RPCStatusCode.ALREADY_EXISTS, b""))
        handle = client.get_schedule_handle.return_value

        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        count = await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        assert count == 1
        client.create_schedule.assert_called_once()
        handle.update.assert_called_once()

    async def test_sync_ignores_non_scheduled_triggers(self) -> None:
        """Non-scheduled trigger nodes should be ignored."""
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(
            triggers=[
                {"id": "trigger_1", "type": "manual_trigger", "parameters": {}},
                {"id": "trigger_2", "type": "webhook_trigger", "parameters": {"webhook_path": "test"}},
            ]
        )

        count = await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        assert count == 0
        client.create_schedule.assert_not_called()

    async def test_sync_multiple_triggers(self) -> None:
        """Should handle multiple scheduled triggers in one workflow."""
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(
            triggers=[
                _make_scheduled_trigger("trigger_1", cron="0 9 * * *"),
                _make_scheduled_trigger("trigger_2", cron="0 17 * * *"),
            ]
        )

        count = await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        assert count == 2
        assert client.create_schedule.call_count == 2

    async def test_sync_rejects_invalid_config(self) -> None:
        """Should raise TriggerValidationError for invalid trigger config."""
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger_1",
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "cron"},  # Missing 'cron' field
                }
            ]
        )

        with pytest.raises(TriggerValidationError):
            await service.sync_scheduled_triggers(
                workflow_id="wf-123",
                workflow_definition=definition,
            )

    async def test_sync_interval_trigger(self) -> None:
        """Should handle interval-type scheduled triggers."""
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(
            triggers=[
                _make_scheduled_trigger(
                    "trigger_1",
                    schedule_type="interval",
                    interval="R/2024-01-01T00:00:00Z/P1D",
                )
            ]
        )

        count = await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        assert count == 1
        client.create_schedule.assert_called_once()

    async def test_sync_deletes_removed_triggers(self) -> None:
        """Should delete Temporal Schedules for trigger nodes removed from the definition."""
        client = _make_mock_client()
        # Simulate search attr query returning both current and stale schedules
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1"),
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_old"),
                ]
            )
        )
        handle = client.get_schedule_handle.return_value
        handle.delete = AsyncMock()

        service = ScheduledTriggerService(temporal_client=client)

        # Definition only has trigger_1 — trigger_old was removed
        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        # Should request handle for the stale schedule and delete it
        client.get_schedule_handle.assert_any_call("orchestrator-sched-wf-123-trigger_old")
        handle.delete.assert_called_once()

    async def test_sync_skips_trigger_with_missing_id(self) -> None:
        """Trigger node without id should be skipped without error."""
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(
            triggers=[
                {"type": "scheduled_trigger", "parameters": {"schedule_type": "cron", "cron": "0 9 * * *"}},
            ]
        )

        count = await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        assert count == 0
        client.create_schedule.assert_not_called()

    @pytest.mark.parametrize("status", [RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED])
    async def test_sync_connection_error_wraps_as_sync_error(self, status: RPCStatusCode) -> None:
        """Connection RPCError should invalidate client cache and raise ScheduledTriggerSyncError."""
        client = _make_mock_client()
        client.create_schedule = AsyncMock(side_effect=RPCError("conn error", status, b""))

        service = ScheduledTriggerService(temporal_client=client)
        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        with pytest.raises(ScheduledTriggerSyncError) as exc_info:
            await service.sync_scheduled_triggers(
                workflow_id="wf-123",
                workflow_definition=definition,
            )

        assert exc_info.value.__cause__ is not None
        assert _mod._cached_client is None
        assert _mod._search_attr_available is None

    async def test_sync_unexpected_rpc_error_reraises(self) -> None:
        """RPCError that is not ALREADY_EXISTS or a connection error should propagate."""
        client = _make_mock_client()
        client.create_schedule = AsyncMock(side_effect=RPCError("internal", RPCStatusCode.INTERNAL, b""))

        service = ScheduledTriggerService(temporal_client=client)
        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        with pytest.raises(ScheduledTriggerSyncError) as exc_info:
            await service.sync_scheduled_triggers(
                workflow_id="wf-123",
                workflow_definition=definition,
            )

        assert isinstance(exc_info.value.__cause__, RPCError)
        assert exc_info.value.__cause__.status == RPCStatusCode.INTERNAL

    async def test_stale_deletion_error_wraps_as_sync_error(self) -> None:
        """RPCError during stale schedule deletion should wrap as ScheduledTriggerSyncError."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1"),
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_old"),
                ]
            )
        )
        handle = client.get_schedule_handle.return_value
        handle.delete = AsyncMock(side_effect=RPCError("internal", RPCStatusCode.INTERNAL, b""))

        service = ScheduledTriggerService(temporal_client=client)
        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        with pytest.raises(ScheduledTriggerSyncError) as exc_info:
            await service.sync_scheduled_triggers(
                workflow_id="wf-123",
                workflow_definition=definition,
            )

        assert exc_info.value.__cause__ is not None


class TestDeleteTriggersForWorkflow:
    """Tests for delete_triggers_for_workflow method."""

    async def test_deletes_temporal_schedules(self) -> None:
        """Should delete all Temporal Schedules found by prefix scan."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1"),
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_2"),
                ]
            )
        )
        handle = client.get_schedule_handle.return_value
        handle.delete = AsyncMock()

        service = ScheduledTriggerService(temporal_client=client)

        deleted = await service.delete_triggers_for_workflow(
            workflow_id="wf-123",
        )

        assert deleted == 2
        assert handle.delete.call_count == 2

    async def test_delete_handles_nonexistent_schedule(self) -> None:
        """Should handle case where schedule doesn't exist."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1"),
                ]
            )
        )
        handle = client.get_schedule_handle.return_value
        handle.delete = AsyncMock(side_effect=RPCError("Schedule not found", RPCStatusCode.NOT_FOUND, b""))

        service = ScheduledTriggerService(temporal_client=client)

        deleted = await service.delete_triggers_for_workflow(
            workflow_id="wf-123",
        )

        assert deleted == 0

    async def test_delete_unexpected_rpc_error_reraises(self) -> None:
        """RPCError that is not NOT_FOUND or a connection error should propagate."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from([_make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1")])
        )
        handle = client.get_schedule_handle.return_value
        handle.delete = AsyncMock(side_effect=RPCError("internal", RPCStatusCode.INTERNAL, b""))

        service = ScheduledTriggerService(temporal_client=client)

        with pytest.raises(ScheduledTriggerSyncError) as exc_info:
            await service.delete_triggers_for_workflow(workflow_id="wf-123")

        assert isinstance(exc_info.value.__cause__, RPCError)
        assert exc_info.value.__cause__.status == RPCStatusCode.INTERNAL

    async def test_aborts_after_connect_without_listing(self) -> None:
        """A republish found after connect must not list or delete schedules."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [_make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1")],
            )
        )
        handle = client.get_schedule_handle.return_value
        service = ScheduledTriggerService(temporal_client=client)

        deleted = await service.delete_triggers_for_workflow(
            workflow_id="wf-123",
            should_abort=AsyncMock(return_value=True),
        )

        assert deleted == 0
        client.list_schedules.assert_not_called()
        handle.delete.assert_not_called()

    async def test_aborts_after_list_without_deleting(self) -> None:
        """A republish found after listing must not delete the listed IDs."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [_make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1")],
            )
        )
        handle = client.get_schedule_handle.return_value
        service = ScheduledTriggerService(temporal_client=client)

        deleted = await service.delete_triggers_for_workflow(
            workflow_id="wf-123",
            should_abort=AsyncMock(side_effect=[False, True]),
        )

        assert deleted == 0
        client.list_schedules.assert_called()
        handle.delete.assert_not_called()

    async def test_aborts_before_remaining_deletes(self) -> None:
        """A republish mid-batch must keep schedules that have not been deleted yet."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1"),
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_2"),
                ]
            )
        )
        handle = client.get_schedule_handle.return_value
        handle.delete = AsyncMock()
        service = ScheduledTriggerService(temporal_client=client)

        deleted = await service.delete_triggers_for_workflow(
            workflow_id="wf-123",
            should_abort=AsyncMock(side_effect=[False, False, False, True]),
        )

        assert deleted == 1
        assert handle.delete.call_count == 1


class TestGracefulTemporalUnavailability:
    """Tests for graceful handling of Temporal unavailability."""

    async def test_sync_raises_when_temporal_unavailable_and_triggers_exist(self) -> None:
        """Should raise ScheduledTriggerSyncError when Temporal is down and scheduled triggers exist."""
        service = ScheduledTriggerService(temporal_client=None)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])
        with (
            patch.object(service, "get_client", return_value=None),
            pytest.raises(ScheduledTriggerSyncError) as exc_info,
        ):
            await service.sync_scheduled_triggers(
                workflow_id="wf-123",
                workflow_definition=definition,
            )

        assert exc_info.value.workflow_id == "wf-123"
        assert exc_info.value.trigger_count == 1

    async def test_sync_returns_zero_when_temporal_unavailable_and_no_triggers(self) -> None:
        """Should return 0 silently when Temporal is down but no scheduled triggers exist."""
        service = ScheduledTriggerService(temporal_client=None)

        with patch.object(service, "get_client", return_value=None):
            count = await service.sync_scheduled_triggers(
                workflow_id="wf-123",
                workflow_definition=_make_workflow_definition(triggers=[]),
            )

        assert count == 0

    @pytest.mark.parametrize("status", [RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED])
    async def test_delete_wraps_connection_error_as_sync_error(self, status: RPCStatusCode) -> None:
        """Connection RPCError during deletion should invalidate cache and wrap as ScheduledTriggerSyncError."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from([_make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1")])
        )
        handle = client.get_schedule_handle.return_value
        handle.delete = AsyncMock(side_effect=RPCError("conn error", status, b""))

        service = ScheduledTriggerService(temporal_client=client)

        with pytest.raises(ScheduledTriggerSyncError) as exc_info:
            await service.delete_triggers_for_workflow(workflow_id="wf-123")

        assert exc_info.value.__cause__ is not None
        assert _mod._cached_client is None
        assert _mod._search_attr_available is None

    async def test_delete_skips_when_temporal_unavailable(self) -> None:
        """Should skip deletion gracefully when Temporal is unavailable."""
        service = ScheduledTriggerService(temporal_client=None)

        with patch.object(service, "get_client", return_value=None):
            deleted = await service.delete_triggers_for_workflow(
                workflow_id="wf-123",
            )

        assert deleted == 0


class TestOverlapPolicyPassthrough:
    """Tests that the overlap policy from the trigger config is set on the Temporal Schedule."""

    @pytest.mark.parametrize(
        ("policy_value", "expected_overlap"),
        [
            ("skip", ScheduleOverlapPolicy.SKIP),
            ("buffer_one", ScheduleOverlapPolicy.BUFFER_ONE),
            ("buffer_all", ScheduleOverlapPolicy.BUFFER_ALL),
            ("allow_all", ScheduleOverlapPolicy.ALLOW_ALL),
            ("cancel_other", ScheduleOverlapPolicy.CANCEL_OTHER),
        ],
    )
    async def test_schedule_created_with_correct_overlap_policy(
        self, policy_value: str, expected_overlap: ScheduleOverlapPolicy
    ) -> None:
        """Each missed_schedule_policy value must produce a Schedule with the correct Temporal overlap policy."""
        client = _make_mock_client()
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(
            triggers=[
                _make_scheduled_trigger(
                    "trigger_1",
                    missed_schedule_policy=policy_value,
                )
            ]
        )

        await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        client.create_schedule.assert_called_once()
        schedule = client.create_schedule.call_args[0][1]
        assert schedule.policy.overlap == expected_overlap


class TestScheduleAlreadyRunningError:
    """Tests for ScheduleAlreadyRunningError handling during create/update.

    Temporal raises this when the schedule's action workflow is in-flight.
    The service must handle it gracefully to avoid 500 errors on publish.
    """

    async def test_create_schedule_already_running_falls_through_to_update(self) -> None:
        """ScheduleAlreadyRunningError on create_schedule should fall through to update."""
        client = _make_mock_client()
        client.create_schedule = AsyncMock(side_effect=ScheduleAlreadyRunningError())
        handle = client.get_schedule_handle.return_value

        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        count = await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        assert count == 1
        handle.update.assert_called_once()

    async def test_update_schedule_already_running_retries(self) -> None:
        """ScheduleAlreadyRunningError on handle.update should retry after delay."""
        client = _make_mock_client()
        client.create_schedule = AsyncMock(side_effect=RPCError("already exists", RPCStatusCode.ALREADY_EXISTS, b""))
        handle = client.get_schedule_handle.return_value
        # First update raises ScheduleAlreadyRunningError, second succeeds
        handle.update = AsyncMock(side_effect=[ScheduleAlreadyRunningError(), None])

        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        sleep_path = "syntara.workflows.services.scheduled_trigger_service.asyncio.sleep"
        with patch(sleep_path, new_callable=AsyncMock) as mock_sleep:
            count = await service.sync_scheduled_triggers(
                workflow_id="wf-123",
                workflow_definition=definition,
            )

        assert count == 1
        assert handle.update.call_count == 2
        mock_sleep.assert_called_once_with(2)

    async def test_update_schedule_already_running_exhausts_retries(self) -> None:
        """ScheduleAlreadyRunningError should propagate after all retries are exhausted."""
        client = _make_mock_client()
        client.create_schedule = AsyncMock(side_effect=RPCError("already exists", RPCStatusCode.ALREADY_EXISTS, b""))
        handle = client.get_schedule_handle.return_value
        handle.update = AsyncMock(side_effect=ScheduleAlreadyRunningError())

        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        sleep_path = "syntara.workflows.services.scheduled_trigger_service.asyncio.sleep"
        with patch(sleep_path, new_callable=AsyncMock), pytest.raises(ScheduleAlreadyRunningError):
            await service.sync_scheduled_triggers(
                workflow_id="wf-123",
                workflow_definition=definition,
            )

        assert handle.update.call_count == 3


class TestSearchAttributeRegistration:
    """Tests for _ensure_search_attribute feature detection and registration."""

    async def test_registers_attribute_when_not_present(self) -> None:
        """Should register OrchestratorWorkflowId and return True."""
        client = _make_mock_client(search_attr_available=False)

        result = await _mod._ensure_search_attribute(client)

        assert result is True
        client.operator_service.add_search_attributes.assert_called_once()

    async def test_skips_registration_when_already_present(self) -> None:
        """Should detect existing attribute and skip registration."""
        client = _make_mock_client(search_attr_available=True)

        result = await _mod._ensure_search_attribute(client)

        assert result is True
        client.operator_service.add_search_attributes.assert_not_called()

    async def test_caches_result_across_calls(self) -> None:
        """Should only call operator_service once, then use cached result."""
        client = _make_mock_client(search_attr_available=True)

        result1 = await _mod._ensure_search_attribute(client)
        result2 = await _mod._ensure_search_attribute(client)

        assert result1 is True
        assert result2 is True
        assert client.operator_service.list_search_attributes.call_count == 1

    @pytest.mark.parametrize("status", [RPCStatusCode.UNIMPLEMENTED, RPCStatusCode.PERMISSION_DENIED])
    async def test_falls_back_on_non_connection_rpc_error(self, status: RPCStatusCode) -> None:
        """Should set _search_attr_available=False on non-connection RPC errors."""
        client = _make_mock_client()
        client.operator_service = _make_mock_operator_service(
            list_raises=RPCError("error", status, b""),
        )

        result = await _mod._ensure_search_attribute(client)

        assert result is False
        assert _mod._search_attr_available is False

    @pytest.mark.parametrize("status", [RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED])
    async def test_connection_errors_fall_back_to_prefix_scan(self, status: RPCStatusCode) -> None:
        """Connection errors from operator service should fall back, not re-raise."""
        client = _make_mock_client(
            list_raises=RPCError("conn error", status, b""),
        )

        result = await _mod._ensure_search_attribute(client)

        assert result is False
        assert _mod._search_attr_available is False

    async def test_wrong_type_falls_back(self) -> None:
        """Should fall back if OrchestratorWorkflowId exists with wrong type."""
        client = _make_mock_client()
        resp = MagicMock()
        resp.custom_attributes = {
            "OrchestratorWorkflowId": IndexedValueType.INDEXED_VALUE_TYPE_TEXT,
        }
        client.operator_service.list_search_attributes = AsyncMock(return_value=resp)

        result = await _mod._ensure_search_attribute(client)

        assert result is False
        client.operator_service.add_search_attributes.assert_not_called()

    async def test_already_exists_race_still_returns_true(self) -> None:
        """Concurrent registration by another replica should still enable the feature."""
        client = _make_mock_client(search_attr_available=False)
        client.operator_service = _make_mock_operator_service(
            attr_registered=False,
            add_raises=RPCError("already exists", RPCStatusCode.ALREADY_EXISTS, b""),
        )

        result = await _mod._ensure_search_attribute(client)

        assert result is True
        assert _mod._search_attr_available is True

    async def test_add_non_connection_error_falls_back(self) -> None:
        """Non-connection error from add_search_attributes should fall back to prefix scan."""
        client = _make_mock_client(search_attr_available=False)
        client.operator_service = _make_mock_operator_service(
            attr_registered=False,
            add_raises=RPCError("denied", RPCStatusCode.PERMISSION_DENIED, b""),
        )

        result = await _mod._ensure_search_attribute(client)

        assert result is False
        assert _mod._search_attr_available is False

    @pytest.mark.parametrize("status", [RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED])
    async def test_add_connection_error_falls_back(self, status: RPCStatusCode) -> None:
        """Connection error from add_search_attributes should fall back, not re-raise."""
        client = _make_mock_client(search_attr_available=False)
        client.operator_service = _make_mock_operator_service(
            attr_registered=False,
            add_raises=RPCError("conn error", status, b""),
        )

        result = await _mod._ensure_search_attribute(client)

        assert result is False
        assert _mod._search_attr_available is False


class TestListWorkflowSchedulesOptimized:
    """Tests for _list_workflow_schedules with search attribute optimization."""

    async def test_uses_query_when_search_attr_available(self) -> None:
        """Should query OrchestratorWorkflowId when search attribute is available."""
        client = _make_mock_client(search_attr_available=True)

        async def _list_side_effect(query: str | None = None) -> AsyncIterator[Any]:
            if query and "OrchestratorWorkflowId" in query:
                return _async_iter_from([_make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1")])
            return _async_iter_from([])

        client.list_schedules = AsyncMock(side_effect=_list_side_effect)

        service = ScheduledTriggerService(temporal_client=client)
        result = await service._list_workflow_schedules(client, "wf-123")

        assert result == {"orchestrator-sched-wf-123-trigger_1"}
        client.list_schedules.assert_called_once_with(query='OrchestratorWorkflowId = "wf-123"')

    async def test_falls_back_to_prefix_scan(self) -> None:
        """Should use prefix scan when search attr not available."""
        client = _make_mock_client(
            list_raises=RPCError("not implemented", RPCStatusCode.UNIMPLEMENTED, b""),
        )
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1"),
                    _make_schedule_list_entry("orchestrator-sched-other-trigger_1"),
                ]
            )
        )

        service = ScheduledTriggerService(temporal_client=client)
        result = await service._list_workflow_schedules(client, "wf-123")

        assert result == {"orchestrator-sched-wf-123-trigger_1"}
        client.list_schedules.assert_called_once_with()

    async def test_query_error_falls_back_to_prefix(self) -> None:
        """Should fall back to prefix scan if all SA queries fail."""
        client = _make_mock_client(search_attr_available=True)

        query_error = RPCError("bad query", RPCStatusCode.INVALID_ARGUMENT, b"")

        async def _list_schedules_side_effect(
            query: str | None = None,
        ) -> AsyncIterator[Any]:
            if query is not None:
                raise query_error
            return _async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-123-trigger_1"),
                    _make_schedule_list_entry("orchestrator-sched-other-trigger_1"),
                ]
            )

        client.list_schedules = AsyncMock(side_effect=_list_schedules_side_effect)

        service = ScheduledTriggerService(temporal_client=client)
        result = await service._list_workflow_schedules(client, "wf-123")

        assert result == {"orchestrator-sched-wf-123-trigger_1"}

    async def test_connection_error_in_query_reraises(self) -> None:
        """Connection errors during query should invalidate cache and re-raise."""
        client = _make_mock_client(search_attr_available=True)
        client.list_schedules = AsyncMock(
            side_effect=RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b""),
        )

        service = ScheduledTriggerService(temporal_client=client)

        with (
            patch("syntara.workflows.services.scheduled_trigger_service._invalidate_client_cache") as mock_invalidate,
            pytest.raises(RPCError),
        ):
            await service._list_workflow_schedules(client, "wf-123")

        mock_invalidate.assert_called()

    async def test_list_schedules_returns_empty_set(self) -> None:
        """Empty schedule list should return empty set."""
        client = _make_mock_client(search_attr_available=True)

        async def _empty_list(query: str | None = None) -> AsyncIterator[Any]:
            return _async_iter_from([])

        client.list_schedules = AsyncMock(side_effect=_empty_list)

        service = ScheduledTriggerService(temporal_client=client)
        result = await service._list_workflow_schedules(client, "wf-123")

        assert result == set()

    @pytest.mark.parametrize("bad_id", ['wf-123" OR 1=1', "wf%bad"])
    async def test_invalid_workflow_id_falls_back_to_prefix_scan(self, bad_id: str) -> None:
        """Invalid workflow_id should skip search attr and fall back to prefix scan."""
        client = _make_mock_client(search_attr_available=True)
        expected_id = f"orchestrator-sched-{bad_id}-trigger_1"
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry(expected_id),
                    _make_schedule_list_entry("orchestrator-sched-other-trigger_1"),
                ]
            )
        )

        service = ScheduledTriggerService(temporal_client=client)
        result = await service._list_workflow_schedules(client, bad_id)

        assert result == {expected_id}
        client.list_schedules.assert_called_once_with()


class TestCreateScheduleWithSearchAttributes:
    """Tests for _create_or_update_schedule with search attributes."""

    async def test_create_passes_search_attributes(self) -> None:
        """Should pass TypedSearchAttributes with OrchestratorWorkflowId to create_schedule."""
        client = _make_mock_client(search_attr_available=True)
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        call_kwargs = client.create_schedule.call_args[1]
        search_attrs = call_kwargs["search_attributes"]
        assert isinstance(search_attrs, TypedSearchAttributes)
        pairs = list(search_attrs)
        assert len(pairs) == 1
        assert pairs[0].key.name == "OrchestratorWorkflowId"
        assert pairs[0].value == "wf-123"

    async def test_update_passes_search_attributes(self) -> None:
        """On ALREADY_EXISTS, should pass search_attributes in ScheduleUpdate."""
        client = _make_mock_client(search_attr_available=True)
        client.create_schedule = AsyncMock(side_effect=RPCError("exists", RPCStatusCode.ALREADY_EXISTS, b""))
        handle = client.get_schedule_handle.return_value

        service = ScheduledTriggerService(temporal_client=client)
        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        handle.update.assert_called_once()
        updater_fn = handle.update.call_args[0][0]
        update_result = updater_fn(MagicMock())
        assert update_result.search_attributes is not None
        pairs = list(update_result.search_attributes)
        assert len(pairs) == 1
        assert pairs[0].key.name == "OrchestratorWorkflowId"

    async def test_create_without_search_attr_when_unavailable(self) -> None:
        """Should pass None search_attributes when feature not available."""
        client = _make_mock_client(
            list_raises=RPCError("not implemented", RPCStatusCode.UNIMPLEMENTED, b""),
        )
        service = ScheduledTriggerService(temporal_client=client)

        definition = _make_workflow_definition(triggers=[_make_scheduled_trigger("trigger_1")])

        await service.sync_scheduled_triggers(
            workflow_id="wf-123",
            workflow_definition=definition,
        )

        call_kwargs = client.create_schedule.call_args[1]
        assert call_kwargs["search_attributes"] is None


class TestGetSharedClient:
    """Tests for _get_shared_client module-level client caching."""

    async def test_returns_cached_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return the cached client without reconnecting."""
        sentinel = MagicMock()
        monkeypatch.setattr(_mod, "_cached_client", sentinel)
        result = await _mod._get_shared_client()
        assert result is sentinel

    async def test_connects_and_caches(self) -> None:
        """Should connect, cache, and return a new client."""
        mock_client = MagicMock()
        with patch(
            "syntara.workflows.services.scheduled_trigger_service.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            result = await _mod._get_shared_client()
        assert result is mock_client
        assert _mod._cached_client is mock_client

    @pytest.mark.parametrize(
        "exc", [OSError("refused"), RuntimeError("boom"), RPCError("down", RPCStatusCode.UNAVAILABLE, b"")]
    )
    async def test_returns_none_on_connection_failure(self, exc: Exception) -> None:
        """Should return None when Temporal is unreachable."""
        with patch(
            "syntara.workflows.services.scheduled_trigger_service.Client.connect",
            new_callable=AsyncMock,
            side_effect=exc,
        ):
            result = await _mod._get_shared_client()
        assert result is None

    async def test_hung_connect_does_not_hold_client_lock(self) -> None:
        """Client.connect must not hold ``_client_lock`` while it is in flight."""
        connect_started = asyncio.Event()

        async def _hang(*_args: object, **_kwargs: object) -> MagicMock:
            connect_started.set()
            await asyncio.Event().wait()
            return MagicMock()

        with patch(
            "syntara.workflows.services.scheduled_trigger_service.Client.connect",
            new=_hang,
        ):
            waiter = asyncio.create_task(_mod._get_shared_client())
            await asyncio.wait_for(connect_started.wait(), timeout=1.0)
            assert not _mod._client_lock.locked()
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.05):
                    await _mod._get_shared_client()
            assert _mod._connect_task is not None
            assert not _mod._connect_task.done()
            assert not waiter.done()
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)

    async def test_invalidate_does_not_drop_in_flight_connect_task(self) -> None:
        """Clearing the cache must not drop the strong ref to an in-flight connect."""
        connect_started = asyncio.Event()
        connect_calls = 0

        async def _hang(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            connect_started.set()
            await asyncio.Event().wait()
            return MagicMock()

        with patch(
            "syntara.workflows.services.scheduled_trigger_service.Client.connect",
            new=_hang,
        ):
            waiter = asyncio.create_task(_mod._get_shared_client())
            await asyncio.wait_for(connect_started.wait(), timeout=1.0)
            in_flight = _mod._connect_task
            assert in_flight is not None
            _mod._invalidate_client_cache()
            later_waiter = asyncio.create_task(_mod._get_shared_client())
            await asyncio.sleep(0.05)
            assert _mod._connect_task is in_flight
            assert not in_flight.done()
            assert connect_calls == 1
            waiter.cancel()
            later_waiter.cancel()
            await asyncio.gather(waiter, later_waiter, return_exceptions=True)

    async def test_invalidate_after_successful_connect_reconnects(self) -> None:
        """A finished connect task must not block reconnect after cache invalidation."""
        first_client = MagicMock()
        second_client = MagicMock()
        with patch(
            "syntara.workflows.services.scheduled_trigger_service.Client.connect",
            new_callable=AsyncMock,
            side_effect=[first_client, second_client],
        ) as mock_connect:
            assert await _mod._get_shared_client() is first_client
            _mod._invalidate_client_cache()
            assert _mod._cached_client is None
            assert await _mod._get_shared_client() is second_client
            assert mock_connect.await_count == 2

    async def test_timed_out_waiter_does_not_cancel_overlapping_sibling(self) -> None:
        """A waiter timeout must leave the shared connect running for later waiters."""
        connect_started = asyncio.Event()
        allow_connect = asyncio.Event()
        client = MagicMock()
        connect_calls = 0

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            connect_started.set()
            await allow_connect.wait()
            return client

        with (
            patch(
                "syntara.workflows.services.scheduled_trigger_service.Client.connect",
                new=_connect,
            ),
            patch("syntara.workflows.services.scheduled_trigger_service._CONNECT_TIMEOUT_SECONDS", 0.25),
        ):
            try:
                first = asyncio.create_task(_mod._get_shared_client())
                await asyncio.wait_for(connect_started.wait(), timeout=1.0)
                await asyncio.sleep(0.05)
                second = asyncio.create_task(_mod._get_shared_client())
                in_flight = _mod._connect_task
                assert in_flight is not None
                assert await asyncio.wait_for(first, timeout=1.0) is None
                assert not in_flight.done()
                assert not in_flight.cancelled()
                assert _mod._connect_task is in_flight
                assert connect_calls == 1
                allow_connect.set()
                assert await asyncio.wait_for(second, timeout=1.0) is client
                assert _mod._cached_client is client
            finally:
                allow_connect.set()

    async def test_stale_replacement_does_not_cancel_joined_waiters(self) -> None:
        """Replacing a stale connect must not cancel waiters still joined to it."""
        connect_started = asyncio.Event()
        replacement_started = asyncio.Event()
        allow_first = asyncio.Event()
        first_client = MagicMock(name="original")
        second_client = MagicMock(name="replacement")
        connect_calls = 0

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                connect_started.set()
                await allow_first.wait()
                return first_client
            replacement_started.set()
            return second_client

        with (
            patch(
                "syntara.workflows.services.scheduled_trigger_service.Client.connect",
                new=_connect,
            ),
            patch("syntara.workflows.services.scheduled_trigger_service._CONNECT_TIMEOUT_SECONDS", 0.4),
        ):
            try:
                first = asyncio.create_task(_mod._get_shared_client())
                await asyncio.wait_for(connect_started.wait(), timeout=1.0)
                await asyncio.sleep(0.05)
                sibling = asyncio.create_task(_mod._get_shared_client())
                original = _mod._connect_task
                assert original is not None
                assert await asyncio.wait_for(first, timeout=1.0) is None
                third = asyncio.create_task(_mod._get_shared_client())
                await asyncio.wait_for(replacement_started.wait(), timeout=1.0)
                assert connect_calls == 2
                assert _mod._connect_task is not original
                assert not original.cancelled()
                allow_first.set()
                assert await asyncio.wait_for(sibling, timeout=1.0) is not None
                assert await asyncio.wait_for(third, timeout=1.0) is not None
                assert connect_calls == 2
            finally:
                allow_first.set()

    async def test_late_connect_success_is_cached_after_waiter_timeout(self) -> None:
        """A slow-but-healthy connect must still be cached after waiters time out."""
        connect_started = asyncio.Event()
        allow_connect = asyncio.Event()
        client = MagicMock()

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            connect_started.set()
            await allow_connect.wait()
            return client

        with (
            patch(
                "syntara.workflows.services.scheduled_trigger_service.Client.connect",
                new=_connect,
            ),
            patch("syntara.workflows.services.scheduled_trigger_service._CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                assert await asyncio.wait_for(_mod._get_shared_client(), timeout=1.0) is None
                in_flight = _mod._connect_task
                assert in_flight is not None
                assert not in_flight.cancelled()
                allow_connect.set()
                assert await asyncio.wait_for(in_flight, timeout=1.0) is client
                assert _mod._cached_client is client
                assert await _mod._get_shared_client() is client
            finally:
                allow_connect.set()

    async def test_timed_out_connect_is_replaced(self) -> None:
        """A hung Client.connect older than the waiter budget is replaced on the next wait."""
        connect_calls = 0
        first_hang = asyncio.Event()
        second_client = MagicMock()

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                await first_hang.wait()
                return MagicMock()
            return second_client

        with (
            patch(
                "syntara.workflows.services.scheduled_trigger_service.Client.connect",
                new=_connect,
            ),
            patch("syntara.workflows.services.scheduled_trigger_service._CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                first = await asyncio.wait_for(_mod._get_shared_client(), timeout=1.0)
                assert first is None
                old_task = _mod._connect_task
                assert old_task is not None
                assert not old_task.done()
                await asyncio.sleep(0.02)
                assert await _mod._get_shared_client() is second_client
                assert connect_calls == 2
                assert not old_task.cancelled()
            finally:
                first_hang.set()
                await asyncio.sleep(0)

    async def test_hung_connect_is_replaced_even_if_connect_ignores_cancel(self) -> None:
        """Replacement must not wait for Client.connect to honour cancellation."""
        connect_calls = 0
        first_hang = asyncio.Event()
        second_client = MagicMock()

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                try:
                    await first_hang.wait()
                except asyncio.CancelledError:
                    await first_hang.wait()
                return MagicMock()
            return second_client

        with (
            patch(
                "syntara.workflows.services.scheduled_trigger_service.Client.connect",
                new=_connect,
            ),
            patch("syntara.workflows.services.scheduled_trigger_service._CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                first = await asyncio.wait_for(_mod._get_shared_client(), timeout=1.0)
                assert first is None
                old_task = _mod._connect_task
                assert old_task is not None
                await asyncio.sleep(0.02)
                assert await _mod._get_shared_client() is second_client
                assert connect_calls == 2
                assert _mod._cached_client is second_client
                assert not old_task.cancelled()
            finally:
                first_hang.set()
                await asyncio.sleep(0)

    async def test_stale_connect_does_not_overwrite_newer_client(self) -> None:
        """A late success from a replaced connect must not replace the new client."""
        connect_calls = 0
        allow_first = asyncio.Event()
        first_client = MagicMock(name="stale")
        second_client = MagicMock(name="fresh")

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                try:
                    await allow_first.wait()
                except asyncio.CancelledError:
                    await allow_first.wait()
                return first_client
            return second_client

        with (
            patch(
                "syntara.workflows.services.scheduled_trigger_service.Client.connect",
                new=_connect,
            ),
            patch("syntara.workflows.services.scheduled_trigger_service._CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                assert await asyncio.wait_for(_mod._get_shared_client(), timeout=1.0) is None
                old_task = _mod._connect_task
                assert old_task is not None
                await asyncio.sleep(0.02)
                assert await _mod._get_shared_client() is second_client
                assert not old_task.cancelled()
                allow_first.set()
                await asyncio.wait_for(old_task, timeout=1.0)
                assert _mod._cached_client is second_client
            finally:
                allow_first.set()

    async def test_replaced_connect_kept_alive_against_gc(self) -> None:
        """A replaced connect must survive GC when only the module set holds it.

        Reproduces the drop-on-the-floor bug: after the first waiter times out,
        the replaced connect is referenced only by ``_pending_connect_tasks``.
        Unlike the sibling replacement tests, this one keeps no local strong
        ref to the old task, so ``gc.collect()`` would cancel it ("Task was
        destroyed but it is pending") without the strong-ref set.
        """
        connect_calls = 0
        allow_first = asyncio.Event()
        first_client = MagicMock(name="stale")
        second_client = MagicMock(name="fresh")

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                await allow_first.wait()
                return first_client
            return second_client

        with (
            patch(
                "syntara.workflows.services.scheduled_trigger_service.Client.connect",
                new=_connect,
            ),
            patch("syntara.workflows.services.scheduled_trigger_service._CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                # First waiter times out; the connect keeps running in the set.
                assert await asyncio.wait_for(_mod._get_shared_client(), timeout=1.0) is None
                stale_ref = weakref.ref(_mod._connect_task)
                stale_task = stale_ref()
                assert stale_task is not None
                assert stale_task in _mod._pending_connect_tasks

                # Replace the stale connect, then drop every local strong ref
                # to it. Only ``_pending_connect_tasks`` should hold it now.
                await asyncio.sleep(0.02)
                assert await _mod._get_shared_client() is second_client
                assert connect_calls == 2
                assert _mod._connect_task is not stale_task
                del stale_task
                gc.collect()

                # Without the strong-ref set the task would be gone/cancelled.
                survivor = stale_ref()
                assert survivor is not None
                assert survivor in _mod._pending_connect_tasks
                assert not survivor.cancelled()

                # A late success from the survivor still completes and, once
                # done, drops itself from the set via the done-callback.
                allow_first.set()
                assert await asyncio.wait_for(survivor, timeout=1.0) is not None
                await asyncio.sleep(0)
                assert survivor not in _mod._pending_connect_tasks
                assert _mod._cached_client is second_client
            finally:
                allow_first.set()


class TestCreateSchedule:
    """Tests for the create_schedule reconciliation helper."""

    async def test_happy_path_returns_schedule_id(self) -> None:
        """Should validate config, create the schedule, and return its deterministic ID."""
        client = _make_mock_client(search_attr_available=True)
        service = ScheduledTriggerService(temporal_client=client)

        schedule_id = await service.create_schedule(
            workflow_id="wf-123",
            trigger_node_id="trigger_1",
            config={"schedule_type": "cron", "cron": "0 9 * * *"},
        )

        assert schedule_id == "orchestrator-sched-wf-123-trigger_1"
        client.create_schedule.assert_called_once()

    async def test_temporal_unavailable_raises_runtime_error(self) -> None:
        """Should raise RuntimeError when Temporal client is unavailable."""
        service = ScheduledTriggerService(temporal_client=None)

        with (
            patch.object(service, "get_client", return_value=None),
            pytest.raises(RuntimeError, match="Temporal client unavailable"),
        ):
            await service.create_schedule(
                workflow_id="wf-123",
                trigger_node_id="trigger_1",
                config={"schedule_type": "cron", "cron": "0 9 * * *"},
            )

    async def test_invalid_config_raises_validation_error(self) -> None:
        """Should raise TriggerValidationError for invalid trigger config."""
        client = _make_mock_client(search_attr_available=True)
        service = ScheduledTriggerService(temporal_client=client)

        with pytest.raises(TriggerValidationError):
            await service.create_schedule(
                workflow_id="wf-123",
                trigger_node_id="trigger_1",
                config={"schedule_type": "cron"},  # Missing 'cron' field
            )


class TestListAllSchedules:
    """Tests for the list_all_schedules method."""

    async def test_uses_query_when_search_attr_available(self) -> None:
        """Should query OrchestratorWorkflowId when search attribute is available."""
        client = _make_mock_client(search_attr_available=True)

        async def _list_side_effect(query: str | None = None) -> AsyncIterator[Any]:
            if query and "OrchestratorWorkflowId" in query:
                return _async_iter_from(
                    [
                        _make_schedule_list_entry("orchestrator-sched-wf-1-t1"),
                        _make_schedule_list_entry("orchestrator-sched-wf-2-t1"),
                    ]
                )
            return _async_iter_from([])

        client.list_schedules = AsyncMock(side_effect=_list_side_effect)

        service = ScheduledTriggerService(temporal_client=client)
        result = await service.list_all_schedules(client)

        assert result == {"orchestrator-sched-wf-1-t1", "orchestrator-sched-wf-2-t1"}
        client.list_schedules.assert_called_once_with(query='OrchestratorWorkflowId != ""')

    async def test_falls_back_to_prefix_scan_when_search_attr_unavailable(self) -> None:
        """Should use prefix scan when search attribute is not available."""
        client = _make_mock_client(
            list_raises=RPCError("not implemented", RPCStatusCode.UNIMPLEMENTED, b""),
        )
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-1-t1"),
                    _make_schedule_list_entry("unrelated-schedule"),
                ]
            )
        )

        service = ScheduledTriggerService(temporal_client=client)
        result = await service.list_all_schedules(client)

        assert result == {"orchestrator-sched-wf-1-t1"}
        client.list_schedules.assert_called_once_with()

    async def test_query_error_falls_back_to_prefix_scan(self) -> None:
        """Non-connection RPCError from all queries should fall back to prefix scan."""
        client = _make_mock_client(search_attr_available=True)

        async def _list_side_effect(query: str | None = None) -> AsyncIterator[Any]:
            if query is not None:
                msg = "bad query"
                raise RPCError(msg, RPCStatusCode.INVALID_ARGUMENT, b"")
            return _async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-1-t1"),
                    _make_schedule_list_entry("other-system-schedule"),
                ]
            )

        client.list_schedules = AsyncMock(side_effect=_list_side_effect)

        service = ScheduledTriggerService(temporal_client=client)
        result = await service.list_all_schedules(client)

        assert result == {"orchestrator-sched-wf-1-t1"}


class TestListSchedulesByPrefix:
    """Tests for the list_schedules_by_prefix static method."""

    async def test_no_prefix_matches_all_managed_schedules(self) -> None:
        """Empty prefix should match orchestrator-sched-* IDs only."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-1-t1"),
                    _make_schedule_list_entry("other-system-schedule"),
                ]
            )
        )

        result = await ScheduledTriggerService.list_schedules_by_prefix(client)

        assert result == {"orchestrator-sched-wf-1-t1"}

    async def test_with_prefix_narrows_to_workflow(self) -> None:
        """Non-empty prefix should match schedules for that workflow."""
        client = _make_mock_client()
        client.list_schedules = AsyncMock(
            return_value=_async_iter_from(
                [
                    _make_schedule_list_entry("orchestrator-sched-wf-123-t1"),
                    _make_schedule_list_entry("other-sched-wf-123-t2"),
                    _make_schedule_list_entry("orchestrator-sched-wf-456-t1"),
                ]
            )
        )

        result = await ScheduledTriggerService.list_schedules_by_prefix(client, "wf-123")

        assert result == {"orchestrator-sched-wf-123-t1"}
