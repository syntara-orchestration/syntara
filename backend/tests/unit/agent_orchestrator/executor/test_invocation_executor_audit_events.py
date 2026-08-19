"""Unit tests for InvocationExecutor audit event dispatch.

Verifies that InvocationExecutor emits the expected audit events during execution:
- InvocationLifecycleEvent (RUNNING, COMPLETED, CANCELLED, FAILED)
"""

from collections.abc import AsyncGenerator
from contextlib import ExitStack, asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.audit.invocation_lifecycle import (
    InvocationLifecycleEvent,
    InvocationLifecycleHandler,
)
from syntara.agent_orchestrator.exceptions import (
    InvocationCancelledError,
    ToolDiscoveryError,
    ToolSelectionUnavailableError,
)
from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor
from syntara.agent_orchestrator.models import Invocation, InvocationStatus
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.events.function_execution import FunctionExecutionEvent, FunctionExecutionHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventStatus
from syntara.core.config.base import Settings
from syntara.core.models.principal import PrincipalType, service_principal_id
from syntara.core.models.user import User


def _make_invocation(**overrides: object) -> Invocation:
    """Build a minimal Invocation for testing."""
    defaults = {
        "id": uuid4(),
        "prompt": "test prompt",
        "session_id": "sess-1",
        "created_by": uuid4(),
        "status": InvocationStatus.CREATED,
        "context_data": {},
        "created_at": datetime.now(UTC),
    }
    data = {**defaults, **overrides}
    return Invocation(**data)


def _make_user(**overrides: object) -> User:
    """Build a minimal User for testing."""
    defaults = {
        "id": uuid4(),
        "username": "testuser",
        "email": "test@example.com",
        "deleted_at": None,
    }
    data = {**defaults, **overrides}
    return User(**data)


class TestInvocationExecutorLifecycleEvents:
    """Tests for InvocationLifecycleEvent dispatch during _execute_orchestration()."""

    def setup_method(self) -> None:
        """Register audit event handlers for InvocationExecutor tests."""
        AuditEventDispatcher.register(
            {
                InvocationLifecycleEvent: InvocationLifecycleHandler(),
                FunctionExecutionEvent: FunctionExecutionHandler(),
            }
        )

    async def _execute_invocation(
        self,
        invocation: Invocation,
        user: User | None,
        mock_orchestration_service: AsyncMock,
        session_get_behavior: AsyncMock | None = None,
        *,
        update_status_if_not_cancelled_return: bool = True,
    ) -> list[AuditEvent]:
        """Generic helper to execute invocation with customizable mocking.

        Args:
            invocation: The invocation to execute
            user: The user to return from session.get(User, ...). If None, simulates unknown user.
            mock_orchestration_service: Pre-configured mock orchestration service
            session_get_behavior: Optional custom session.get() behavior. If None, uses default.
            update_status_if_not_cancelled_return: Return value for
                _update_invocation_status_if_not_cancelled. Default is True.
                Use False to simulate cancellation during execution.

        Returns:
            List of emitted AuditEvents

        """
        # Mock session to handle get() calls for both Invocation and User
        mock_session = AsyncMock()

        if session_get_behavior is not None:
            mock_session.get = session_get_behavior
        else:
            # Default behavior: return invocation for Invocation lookups, user for User lookups
            def session_get_side_effect(model_class: type, _: object) -> object:
                if model_class == Invocation:
                    return invocation
                if model_class == User:
                    return user
                return None

            mock_session.get.side_effect = session_get_side_effect

        # Mock session.exec() for status update operations
        # exec() is async and returns a result object with first() method (non-async) and rowcount
        mock_exec_result = Mock()
        mock_exec_result.first.return_value = invocation
        mock_exec_result.rowcount = 1  # Simulate successful update

        async def mock_exec_func(*args: object, **kwargs: object) -> Mock:
            return mock_exec_result

        mock_session.exec = mock_exec_func

        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        # Mock session context manager factory
        @asynccontextmanager
        async def mock_session_context() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor()

        patches = [
            patch("syntara.audit.emitter._do_emit_audit_event"),
            patch.object(executor, "get_async_session_context", side_effect=lambda: mock_session_context()),
            patch.object(executor, "_init_orchestration", return_value=(mock_orchestration_service, None)),
            patch.object(
                executor,
                "_complete_invocation_if_not_cancelled",
                return_value=update_status_if_not_cancelled_return,
            ),
            patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value="backend.ao.svc"),
        ]

        with ExitStack() as stack:
            mock_do_emit = stack.enter_context(patches[0])
            for p in patches[1:]:
                stack.enter_context(p)

            await executor.execute_invocation(invocation_id=invocation.id)

        # Return all emitted events for test-specific assertions
        return [call.args[0] for call in mock_do_emit.call_args_list]

    async def _run_successful_execution_lifecycle_test(self, user: User | None) -> None:
        """Helper to test RUNNING and COMPLETED event emission with different user scenarios.

        Args:
            user: The user to associate with the invocation. If None, simulates unknown user scenario.

        """
        execution_id = uuid4()

        # When user is None, we still need a user ID for invocation.created_by
        # but session.get(User, ...) will return None to simulate lookup failure
        test_user = user if user is not None else _make_user()

        invocation = _make_invocation(
            created_by=test_user.id,
            context_data={"execution_id": str(execution_id)},
        )

        # Mock orchestration service
        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(return_value={"content": "result", "llm_token_usage_log": []})

        events = await self._execute_invocation(
            invocation=invocation,
            user=user,
            mock_orchestration_service=mock_orchestration_service,
        )

        # Determine expected actor fields based on whether user exists
        if user is not None:
            expected_actor_id: UUID = user.id
            expected_actor_username: str = user.username
            expected_actor_type: PrincipalType = PrincipalType.USER
        else:
            expected_actor_id = service_principal_id("backend.ao.svc")
            expected_actor_username = "backend.ao.svc"
            expected_actor_type = PrincipalType.SERVICE

        # Verify events: RUNNING, COMPLETED
        assert len(events) == 2

        # Filter to InvocationLifecycleEvents
        lifecycle_events = [e for e in events if e.event_action in ["invocation_running", "invocation_completed"]]
        assert len(lifecycle_events) == 2

        # Event 1: RUNNING
        assert lifecycle_events[0].event_action == "invocation_running"
        assert lifecycle_events[0].event_category == EventCategory.AGENT_INTERACTION
        assert lifecycle_events[0].event_status == EventStatus.SUCCESS
        assert lifecycle_events[0].structured_data.invocation_status == InvocationStatus.RUNNING  # type: ignore[attr-defined]
        assert lifecycle_events[0].execution_id == execution_id
        assert lifecycle_events[0].actor_id == expected_actor_id
        assert lifecycle_events[0].actor_username == expected_actor_username
        assert lifecycle_events[0].actor_type == expected_actor_type

        # Event 2: COMPLETED
        assert lifecycle_events[1].event_action == "invocation_completed"
        assert lifecycle_events[1].structured_data.invocation_status == InvocationStatus.COMPLETED  # type: ignore[attr-defined]
        assert lifecycle_events[1].structured_data.model_name is None  # type: ignore[attr-defined]
        assert lifecycle_events[1].actor_id == expected_actor_id
        assert lifecycle_events[1].actor_username == expected_actor_username
        assert lifecycle_events[1].actor_type == expected_actor_type

    @pytest.mark.asyncio
    async def test_execute_orchestration_emits_running_and_completed_events(self) -> None:
        """Successful execution emits RUNNING and COMPLETED InvocationLifecycleEvents."""
        user = _make_user()
        await self._run_successful_execution_lifecycle_test(user=user)

    @pytest.mark.asyncio
    async def test_execute_orchestration_emits_running_and_completed_events_with_deleted_user(self) -> None:
        """Successful execution with deleted user emits RUNNING and COMPLETED InvocationLifecycleEvents."""
        user = _make_user()
        user.deleted_at = datetime.now(UTC)
        await self._run_successful_execution_lifecycle_test(user=user)

    @pytest.mark.asyncio
    async def test_execute_orchestration_emits_running_and_completed_events_with_unknown_user(self) -> None:
        """Successful execution with unknown user emits RUNNING and COMPLETED events with SERVICE actor."""
        await self._run_successful_execution_lifecycle_test(user=None)

    @pytest.mark.asyncio
    async def test_execute_orchestration_emits_cancelled_event(self) -> None:
        """Cancelled invocation emits RUNNING and CANCELLED InvocationLifecycleEvents."""
        execution_id = uuid4()
        user = _make_user()

        invocation = _make_invocation(
            created_by=user.id,
            status=InvocationStatus.RUNNING,
            context_data={"execution_id": str(execution_id)},
        )

        # Mock orchestration service
        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(return_value={"content": "result", "llm_token_usage_log": []})

        # Simulate invocation being cancelled during execution by making the conditional update fail
        events = await self._execute_invocation(
            invocation=invocation,
            user=user,
            mock_orchestration_service=mock_orchestration_service,
            update_status_if_not_cancelled_return=False,
        )

        lifecycle_events = [e for e in events if e.event_action in ["invocation_running", "invocation_cancelled"]]

        # Should have RUNNING and CANCELLED
        assert len(lifecycle_events) == 2
        assert lifecycle_events[0].event_action == "invocation_running"
        assert lifecycle_events[0].actor_id == user.id
        assert lifecycle_events[0].actor_username == user.username
        assert lifecycle_events[0].actor_type == PrincipalType.USER

        assert lifecycle_events[1].event_action == "invocation_cancelled"
        assert lifecycle_events[1].structured_data.invocation_status == InvocationStatus.CANCELLED  # type: ignore[attr-defined]
        assert lifecycle_events[1].actor_id == user.id
        assert lifecycle_events[1].actor_username == user.username
        assert lifecycle_events[1].actor_type == PrincipalType.USER

    @pytest.mark.asyncio
    async def test_execute_orchestration_emits_failed_event_on_exception(self) -> None:
        """Failed execution emits RUNNING event followed by FAILED event via error handler."""
        execution_id = uuid4()
        user = _make_user()

        invocation = _make_invocation(
            created_by=user.id,
            context_data={"execution_id": str(execution_id)},
        )

        # Mock orchestration service to raise exception
        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(side_effect=RuntimeError("Execution failed"))

        events = await self._execute_invocation(
            invocation=invocation,
            user=user,
            mock_orchestration_service=mock_orchestration_service,
        )

        lifecycle_events = [e for e in events if e.event_action in ["invocation_running", "invocation_failed"]]

        # Should have RUNNING and FAILED
        assert len(lifecycle_events) == 2
        assert lifecycle_events[0].event_action == "invocation_running"
        assert lifecycle_events[0].actor_id == user.id
        assert lifecycle_events[0].actor_username == user.username
        assert lifecycle_events[0].actor_type == PrincipalType.USER

        assert lifecycle_events[1].event_action == "invocation_failed"
        assert lifecycle_events[1].structured_data.invocation_status == InvocationStatus.FAILED  # type: ignore[attr-defined]
        assert lifecycle_events[1].structured_data.error_type == "RuntimeError"
        assert lifecycle_events[1].actor_id == user.id
        assert lifecycle_events[1].actor_username == user.username
        assert lifecycle_events[1].actor_type == PrincipalType.USER

    @pytest.mark.asyncio
    async def test_execute_orchestration_includes_model_name_in_completed_event(self) -> None:
        """COMPLETED event includes model_name when available."""
        execution_id = uuid4()
        user = _make_user()

        invocation = _make_invocation(
            created_by=user.id,
            context_data={"execution_id": str(execution_id)},
        )

        # Return result with model metadata
        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(
            return_value={
                "content": "result",
                "response_metadata": {"model": "gpt-4"},
                "llm_token_usage_log": [],
            }
        )

        events = await self._execute_invocation(
            invocation=invocation,
            user=user,
            mock_orchestration_service=mock_orchestration_service,
        )

        completed_events = [e for e in events if e.event_action == "invocation_completed"]

        assert len(completed_events) == 1
        assert completed_events[0].structured_data.model_name == "gpt-4"  # type: ignore[attr-defined]
        assert completed_events[0].actor_id == user.id
        assert completed_events[0].actor_username == user.username
        assert completed_events[0].actor_type == PrincipalType.USER

    @pytest.mark.asyncio
    async def test_execute_orchestration_no_cancelled_event_on_invocation_cancelled_error(self) -> None:
        """InvocationCancelledError during execution does not emit duplicate CANCELLED event."""
        execution_id = uuid4()
        user = _make_user()

        invocation = _make_invocation(
            created_by=user.id,
            status=InvocationStatus.RUNNING,
            context_data={"execution_id": str(execution_id)},
        )

        # Orchestration service raises InvocationCancelledError
        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(
            side_effect=InvocationCancelledError(invocation_id=str(invocation.id), phase="execution")
        )

        events = await self._execute_invocation(
            invocation=invocation,
            user=user,
            mock_orchestration_service=mock_orchestration_service,
        )

        # Should only have RUNNING event (no FAILED or duplicate CANCELLED)
        lifecycle_events = [
            e for e in events if e.event_action in ["invocation_running", "invocation_cancelled", "invocation_failed"]
        ]
        assert len(lifecycle_events) == 1
        assert lifecycle_events[0].event_action == "invocation_running"
        assert lifecycle_events[0].actor_id == user.id
        assert lifecycle_events[0].actor_username == user.username
        assert lifecycle_events[0].actor_type == PrincipalType.USER

    @pytest.mark.asyncio
    async def test_handle_execution_error_emits_failed_event(self) -> None:
        """Exception during orchestration triggers _fail_invocation_status_if_not_cancelled and emits FAILED event."""
        execution_id = uuid4()
        request_id = uuid4()
        user = _make_user()

        invocation = _make_invocation(
            created_by=user.id,
            context_data={"execution_id": str(execution_id), "metadata": {"request_id": str(request_id)}},
        )

        # Mock orchestration service to raise exception
        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(side_effect=ValueError("Test error"))

        # Mock session to handle status updates
        mock_session = AsyncMock()

        def session_get_side_effect(model_class: type, _: object) -> object:
            if model_class == Invocation:
                return invocation
            if model_class == User:
                return user
            return None

        mock_session.get.side_effect = session_get_side_effect

        # Mock session.exec() for status update operations
        mock_exec_result = Mock()
        mock_exec_result.rowcount = 1  # Simulate successful update (not cancelled)
        mock_session.exec = AsyncMock(return_value=mock_exec_result)
        mock_session.commit = AsyncMock()

        # Mock session context manager factory
        @asynccontextmanager
        async def mock_session_context() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor()

        # Mock WorkflowSignalClient to prevent actual signal sending
        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch.object(executor, "get_async_session_context", side_effect=lambda: mock_session_context()),
            patch.object(executor, "_init_orchestration", return_value=(mock_orchestration_service, None)),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_failure_signal",
                new_callable=AsyncMock,
            ),
        ):
            await executor.execute_invocation(invocation_id=invocation.id)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        lifecycle_events = [e for e in events if e.event_action in ["invocation_running", "invocation_failed"]]

        # Should have RUNNING and FAILED events
        assert len(lifecycle_events) == 2

        # Event 1: RUNNING
        assert lifecycle_events[0].event_action == "invocation_running"
        assert lifecycle_events[0].actor_id == user.id
        assert lifecycle_events[0].actor_username == user.username
        assert lifecycle_events[0].actor_type == PrincipalType.USER

        # Event 2: FAILED (triggered by _fail_invocation_status_if_not_cancelled)
        assert lifecycle_events[1].event_action == "invocation_failed"
        assert lifecycle_events[1].structured_data.invocation_status == InvocationStatus.FAILED  # type: ignore[attr-defined]
        assert lifecycle_events[1].structured_data.error_type == "ValueError"
        assert lifecycle_events[1].execution_id == execution_id
        assert lifecycle_events[1].structured_data.request_id == str(request_id)  # type: ignore[attr-defined]
        assert lifecycle_events[1].actor_id == user.id
        assert lifecycle_events[1].actor_username == user.username
        assert lifecycle_events[1].actor_type == PrincipalType.USER

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "leaked_fragment", "safe_fragment"),
        [
            (
                ToolDiscoveryError("ConnectionError contacting http://tool-manager.internal/v1/tools"),
                "tool-manager.internal",
                "Required tools could not be discovered or provisioned.",
            ),
            (
                ToolSelectionUnavailableError("unavailable tool IDs: ['aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee']"),
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "None of the requested tools could be provisioned.",
            ),
        ],
    )
    async def test_fail_invocation_error_message_uses_classified_detail_for_tool_errors(
        self,
        error: Exception,
        leaked_fragment: str,
        safe_fragment: str,
    ) -> None:
        """Discovery/selection failures must not write raw exception text to invocation.error_message."""
        user = _make_user()
        invocation = _make_invocation(created_by=user.id)

        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(side_effect=error)

        mock_session = AsyncMock()

        def session_get_side_effect(model_class: type, _: object) -> object:
            if model_class == Invocation:
                return invocation
            if model_class == User:
                return user
            return None

        mock_session.get.side_effect = session_get_side_effect
        mock_exec_result = Mock()
        mock_exec_result.rowcount = 1
        mock_session.exec = AsyncMock(return_value=mock_exec_result)
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def mock_session_context() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor()
        fail_invocation = AsyncMock(return_value=True)

        with (
            patch("syntara.audit.emitter._do_emit_audit_event"),
            patch.object(executor, "get_async_session_context", side_effect=lambda: mock_session_context()),
            patch.object(executor, "_init_orchestration", return_value=(mock_orchestration_service, None)),
            patch.object(executor, "_fail_invocation_if_not_cancelled", fail_invocation),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_failure_signal",
                new_callable=AsyncMock,
            ),
        ):
            await executor.execute_invocation(invocation_id=invocation.id)

        fail_invocation.assert_awaited_once()
        await_args = fail_invocation.await_args
        assert await_args is not None
        error_message = await_args.kwargs["error_message"]
        assert safe_fragment in error_message
        assert leaked_fragment not in error_message
        assert str(error) not in error_message

    @pytest.mark.asyncio
    async def test_handle_execution_error_no_failed_event_when_cancelled(self) -> None:
        """Exception during cancelled invocation does not emit FAILED event (race condition prevented)."""
        execution_id = uuid4()
        user = _make_user()

        invocation = _make_invocation(
            created_by=user.id,
            context_data={"execution_id": str(execution_id)},
        )

        # Mock orchestration service to raise exception
        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(side_effect=ValueError("Test error"))

        # Mock session to handle status updates
        mock_session = AsyncMock()

        def session_get_side_effect(model_class: type, _: object) -> object:
            if model_class == Invocation:
                return invocation
            if model_class == User:
                return user
            return None

        mock_session.get.side_effect = session_get_side_effect

        # Mock session.exec() to simulate invocation becoming cancelled after RUNNING
        # First call (RUNNING status update): success (rowcount = 1)
        # Second call (FAILED status update): failure (rowcount = 0, already CANCELLED)
        mock_exec_result_success = Mock()
        mock_exec_result_success.rowcount = 1  # First call succeeds

        mock_exec_result_cancelled = Mock()
        mock_exec_result_cancelled.rowcount = 0  # Second call fails (already cancelled)

        mock_session.exec = AsyncMock(side_effect=[mock_exec_result_success, mock_exec_result_cancelled])
        mock_session.commit = AsyncMock()

        # Mock session context manager factory
        @asynccontextmanager
        async def mock_session_context() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor()

        # Mock WorkflowSignalClient to prevent actual signal sending
        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch.object(executor, "get_async_session_context", side_effect=lambda: mock_session_context()),
            patch.object(executor, "_init_orchestration", return_value=(mock_orchestration_service, None)),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_failure_signal",
                new_callable=AsyncMock,
            ),
        ):
            await executor.execute_invocation(invocation_id=invocation.id)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        lifecycle_events = [e for e in events if e.event_action in ["invocation_running", "invocation_failed"]]

        # Should only have RUNNING event
        # (no FAILED event because _fail_invocation_status_if_not_cancelled returned False)
        assert len(lifecycle_events) == 1
        assert lifecycle_events[0].event_action == "invocation_running"
        assert lifecycle_events[0].actor_id == user.id
        assert lifecycle_events[0].actor_username == user.username
        assert lifecycle_events[0].actor_type == PrincipalType.USER

    @pytest.mark.asyncio
    async def test_invocation_lifecycle_events_includes_context_identifiers(self) -> None:
        """All lifecycle events include session_id, invocation_id, execution_id, request_id and resource_urn."""
        execution_id = uuid4()
        request_id = uuid4()
        session_id = "sess-lifecycle-schema"
        user = _make_user()

        invocation = _make_invocation(
            created_by=user.id,
            session_id=session_id,
            context_data={"execution_id": str(execution_id), "metadata": {"request_id": str(request_id)}},
        )

        # Mock orchestration service
        mock_orchestration_service = AsyncMock()
        mock_orchestration_service.execute = AsyncMock(return_value={"content": "result", "llm_token_usage_log": []})

        events = await self._execute_invocation(
            invocation=invocation,
            user=user,
            mock_orchestration_service=mock_orchestration_service,
        )

        lifecycle_events = [e for e in events if e.event_action in ["invocation_running", "invocation_completed"]]

        # Verify both RUNNING and COMPLETED events
        assert len(lifecycle_events) == 2

        for event in lifecycle_events:
            # Verify session_id is redacted in structured_data
            assert event.structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
            # Verify invocation_id is included
            assert event.structured_data.invocation_id == str(invocation.id)  # type: ignore[attr-defined]
            # Verify execution_id is included
            assert event.execution_id == execution_id
            # Verify request_id is included (stored as string in audit structured_data)
            assert event.structured_data.request_id == str(request_id)  # type: ignore[attr-defined]
            # Verify resource_urn
            assert event.resource_urn == f"urn:syntara:invocation:{invocation.id}"
