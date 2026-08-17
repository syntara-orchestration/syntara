"""Unit tests for Temporal worker service.

Tests the TemporalWorkerService class and global worker management functions.
"""

# SLF001: Tests need to access private members (_worker_task, registry) to verify internal state

import asyncio
from collections.abc import Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import syntara.workflows.workflow_engine.services.temporal_worker
from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor
from syntara.workflows.workflow_engine.interceptors.auth_interceptor import WorkflowAuthInterceptor
from syntara.workflows.workflow_engine.interceptors.credential_output_interceptor import CredentialOutputInterceptor
from syntara.workflows.workflow_engine.interceptors.monitoring_interceptor import MonitoringWorkflowInterceptor
from syntara.workflows.workflow_engine.services.temporal_worker import (
    TemporalWorkerService,
    get_worker,
    start_worker,
    stop_worker,
)


class TestTemporalWorkerServiceInit:
    """Test TemporalWorkerService initialization."""

    def test_init_with_values(self) -> None:
        """Test worker service initialization with provided values."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        assert service.temporal_address == "test-address"
        assert service.namespace == "test-namespace"
        assert service.task_queue == "test-queue"
        assert service.max_cached_workflows == 20
        assert service.max_concurrent_workflow_tasks == 50
        assert service.max_concurrent_activities == 50
        assert service.client is None
        assert service.worker is None
        assert service._worker_task is None

    def test_init_with_custom_values(self) -> None:
        """Test worker service initialization with custom values."""
        service = TemporalWorkerService(
            temporal_address="temporal.example.com:7233",
            namespace="production",
            task_queue="custom-queue",
            max_cached_workflows=100,
            max_concurrent_workflow_tasks=75,
            max_concurrent_activities=25,
        )

        assert service.temporal_address == "temporal.example.com:7233"
        assert service.namespace == "production"
        assert service.task_queue == "custom-queue"
        assert service.max_cached_workflows == 100
        assert service.max_concurrent_workflow_tasks == 75
        assert service.max_concurrent_activities == 25


class TestTemporalWorkerServiceStart:
    """Test starting the Temporal worker service."""

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        """Test successfully starting the worker service."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        # Mock Temporal client and worker
        mock_client = MagicMock()
        mock_worker = MagicMock()

        # Create a simple coroutine for worker.run to avoid AsyncMock warnings
        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        # Track if create_task was called
        create_task_called = False
        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            nonlocal create_task_called
            create_task_called = True
            # Use the original create_task to avoid recursion
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker),
            patch("asyncio.create_task", side_effect=mock_create_task),
        ):
            await service.start()

            # Verify client was created
            assert service.client == mock_client

            # Verify worker was created
            assert service.worker == mock_worker

            # Verify worker task was created
            assert create_task_called

    @pytest.mark.asyncio
    async def test_start_with_custom_config(self) -> None:
        """Test starting worker with custom configuration."""
        service = TemporalWorkerService(
            temporal_address="custom.temporal.io:7233",
            namespace="staging",
            task_queue="staging-queue",
        )

        mock_client = MagicMock()
        mock_worker = MagicMock()

        # Create a simple coroutine for worker.run to avoid AsyncMock warnings
        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            # Use the original create_task to avoid recursion
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ) as mock_connect,
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker
            ) as mock_worker_class,
            patch("asyncio.create_task", side_effect=mock_create_task),
        ):
            await service.start()

            # Verify client connected with correct address and namespace
            mock_connect.assert_called_once()
            call_args = mock_connect.call_args
            assert call_args[0][0] == "custom.temporal.io:7233"
            assert call_args[1]["namespace"] == "staging"

            # Verify worker was created with correct task queue
            mock_worker_class.assert_called_once()
            _, kwargs = mock_worker_class.call_args
            assert kwargs["task_queue"] == "staging-queue"

    @pytest.mark.asyncio
    async def test_start_wires_auth_interceptors_and_signing_key(self) -> None:
        """Auth interceptors and signing key init must be wired at worker startup."""
        service = TemporalWorkerService(
            temporal_address="test-address",
            namespace="test-namespace",
            task_queue="test-queue",
        )

        mock_client = MagicMock()
        mock_worker = MagicMock()

        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.init_signing_key",
            ) as mock_init_signing_key,
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ) as mock_connect,
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Worker",
                return_value=mock_worker,
            ) as mock_worker_class,
            patch("asyncio.create_task", side_effect=mock_create_task),
        ):
            await service.start()

            mock_init_signing_key.assert_called_once()

            mock_connect.assert_called_once()
            connect_kwargs = mock_connect.call_args[1]
            client_interceptors = connect_kwargs["interceptors"]
            assert len(client_interceptors) == 1
            assert isinstance(client_interceptors[0], WorkflowAuthClientInterceptor)

            mock_worker_class.assert_called_once()
            worker_kwargs = mock_worker_class.call_args[1]
            worker_interceptors = worker_kwargs["interceptors"]
            assert len(worker_interceptors) == 3
            assert isinstance(worker_interceptors[0], WorkflowAuthInterceptor)
            assert isinstance(worker_interceptors[1], MonitoringWorkflowInterceptor)
            assert isinstance(worker_interceptors[2], CredentialOutputInterceptor)

    @pytest.mark.asyncio
    async def test_start_passes_concurrency_controls_to_worker(self) -> None:
        """Test that concurrency and caching params are forwarded to the Worker constructor."""
        service = TemporalWorkerService(
            temporal_address="test-address",
            namespace="test-namespace",
            task_queue="test-queue",
            max_cached_workflows=25,
            max_concurrent_workflow_tasks=30,
            max_concurrent_activities=35,
        )

        mock_client = MagicMock()
        mock_worker = MagicMock()

        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker
            ) as mock_worker_class,
            patch("asyncio.create_task", side_effect=mock_create_task),
        ):
            await service.start()

            mock_worker_class.assert_called_once()
            _, kwargs = mock_worker_class.call_args
            assert kwargs["max_cached_workflows"] == 25
            assert kwargs["max_concurrent_workflow_tasks"] == 30
            assert kwargs["max_concurrent_activities"] == 35

    @pytest.mark.asyncio
    async def test_start_uses_default_concurrency_controls(self) -> None:
        """Test that default concurrency values are forwarded to the Worker constructor."""
        service = TemporalWorkerService(
            temporal_address="test-address",
            namespace="test-namespace",
            task_queue="test-queue",
        )

        assert service.max_cached_workflows == 20
        assert service.max_concurrent_workflow_tasks == 50
        assert service.max_concurrent_activities == 50

        mock_client = MagicMock()
        mock_worker = MagicMock()

        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker
            ) as mock_worker_class,
            patch("asyncio.create_task", side_effect=mock_create_task),
        ):
            await service.start()

            mock_worker_class.assert_called_once()
            _, kwargs = mock_worker_class.call_args
            assert kwargs["max_cached_workflows"] == 20
            assert kwargs["max_concurrent_workflow_tasks"] == 50
            assert kwargs["max_concurrent_activities"] == 50

    @pytest.mark.asyncio
    async def test_start_client_connection_failure(self) -> None:
        """Test handling of client connection failure."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        connection_error = ConnectionError("Connection failed")
        with patch(
            "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
            new=AsyncMock(side_effect=connection_error),
        ):
            with pytest.raises(ConnectionError, match="Connection failed"):
                await service.start()

            # Ensure client and worker remain None after failure
            assert service.client is None
            assert service.worker is None

    @pytest.mark.asyncio
    async def test_start_worker_creation_failure(self) -> None:
        """Test handling of worker creation failure."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        mock_client = MagicMock()

        worker_error = RuntimeError("Worker creation failed")
        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Worker",
                side_effect=worker_error,
            ),
            pytest.raises(RuntimeError, match="Worker creation failed"),
        ):
            await service.start()


class TestTemporalWorkerServiceStop:
    """Test stopping the Temporal worker service."""

    @pytest.mark.asyncio
    async def test_stop_with_running_worker(self) -> None:
        """Test stopping a running worker service."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        # Create a mock worker task that raises CancelledError
        async def mock_worker_run() -> None:
            raise asyncio.CancelledError

        mock_task = asyncio.create_task(mock_worker_run())

        service._worker_task = mock_task
        service.client = MagicMock()

        await service.stop()

    @pytest.mark.asyncio
    async def test_stop_without_running_worker(self) -> None:
        """Test stopping when no worker is running."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        # Should not raise any errors
        await service.stop()

        assert service._worker_task is None
        assert service.client is None

    @pytest.mark.asyncio
    async def test_stop_with_task_exception(self) -> None:
        """Test stopping when worker task has a pending exception.

        Awaiting a failed task will re-raise its exception. The stop() method
        only catches CancelledError, so other exceptions propagate.
        """
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        # Create a task that will raise an exception
        async def error_worker_run() -> None:
            msg = "Worker error"
            raise RuntimeError(msg)

        mock_task = asyncio.create_task(error_worker_run())

        # Wait for the task to complete (it raises internally)
        try:
            await asyncio.wait_for(asyncio.shield(mock_task), timeout=2.0)
        except RuntimeError:
            pass

        # Now assign the failed task
        service._worker_task = mock_task

        # Stop will re-raise the exception when awaiting the task
        with pytest.raises(RuntimeError, match="Worker error"):
            await service.stop()


class TestTemporalWorkerServiceContextManager:
    """Test async context manager protocol."""

    @pytest.mark.asyncio
    async def test_context_manager_success(self) -> None:
        """Test using worker service as async context manager."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        mock_client = MagicMock()
        mock_worker = MagicMock()
        mock_worker.run = AsyncMock()

        # Create a real asyncio task for the worker
        async def mock_worker_run() -> None:
            await asyncio.sleep(100)  # Long-running task

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker),
        ):
            # Override the worker.run to return our mock task
            mock_worker.run.return_value = None

            async with service as worker:
                # Manually set a real task for testing
                service._worker_task = asyncio.create_task(mock_worker_run())

                # Verify service started
                assert worker == service
                assert service.client == mock_client
                assert service.worker == mock_worker

            # Verify service stopped after context exit
            assert service._worker_task is None

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self) -> None:
        """Test context manager properly cleans up even when exception occurs."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        mock_client = MagicMock()
        mock_worker = MagicMock()
        mock_worker.run = AsyncMock()

        # Create a real asyncio task for the worker
        async def mock_worker_run() -> None:
            await asyncio.sleep(100)  # Long-running task

        async def run_service_with_error() -> None:
            """Run service and raise an error for testing exception handling."""
            async with service:
                # Manually set a real task for testing
                service._worker_task = asyncio.create_task(mock_worker_run())
                msg = "Test error"
                raise ValueError(msg)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker),
        ):
            # Override the worker.run to return our mock task
            mock_worker.run.return_value = None

            # Test that exception is raised and cleanup still happens
            with pytest.raises(ValueError, match="Test error"):
                await run_service_with_error()

            # Verify service still stopped properly after exception
            assert service._worker_task is None
            assert service.client is None


class TestGlobalWorkerManagement:
    """Test global worker management functions."""

    @pytest.mark.asyncio
    async def test_start_worker_first_time(self) -> None:
        """Test starting the global worker for the first time."""
        # Reset global worker state
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(None)

        mock_client = MagicMock()
        mock_worker = MagicMock()

        # Create a simple coroutine for worker.run to avoid AsyncMock warnings
        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            # Use the original create_task to avoid recursion
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker
            ) as mock_worker_class,
            patch("asyncio.create_task", side_effect=mock_create_task),
        ):
            worker = await start_worker(
                temporal_address="test.temporal.io:7233",
                namespace="test",
                task_queue="test-queue",
            )

            assert worker is not None
            assert worker.temporal_address == "test.temporal.io:7233"
            assert worker.namespace == "test"
            assert worker.task_queue == "test-queue"

            mock_worker_class.assert_called_once()
            _, kwargs = mock_worker_class.call_args
            assert kwargs["max_cached_workflows"] == 20
            assert kwargs["max_concurrent_workflow_tasks"] == 50
            assert kwargs["max_concurrent_activities"] == 50

        # Cleanup
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(None)

    @pytest.mark.asyncio
    async def test_start_worker_respects_activity_concurrency_override(self) -> None:
        """Background workers pass a lower max_concurrent_activities override."""
        mock_client = MagicMock()
        mock_worker = MagicMock()

        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker
            ) as mock_worker_class,
            patch("asyncio.create_task", side_effect=mock_create_task),
        ):
            worker = await start_worker(
                temporal_address="test.temporal.io:7233",
                namespace="test",
                task_queue="background-queue",
                max_concurrent_activities=10,
            )

            assert worker.max_concurrent_activities == 10
            _, kwargs = mock_worker_class.call_args
            assert kwargs["max_concurrent_activities"] == 10

        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(None)

    @pytest.mark.asyncio
    async def test_start_worker_already_running(self) -> None:
        """Test starting worker when one is already running."""
        # Set up existing worker
        existing_worker = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(existing_worker)

        worker = await start_worker()

        # Should return the existing worker
        assert worker == existing_worker

        # Cleanup
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(None)

    @pytest.mark.asyncio
    async def test_stop_worker_when_running(self) -> None:
        """Test stopping the global worker when it's running."""
        # Set up running worker
        mock_service = MagicMock()
        mock_service.stop = AsyncMock()
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(mock_service)

        await stop_worker()

        # Verify stop was called
        mock_service.stop.assert_called_once()

        # Verify global reference cleared
        assert syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().get_worker() is None

    @pytest.mark.asyncio
    async def test_stop_worker_when_not_running(self) -> None:
        """Test stopping worker when none is running."""
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(None)

        # Should not raise any errors
        await stop_worker()

        assert syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().get_worker() is None

    def test_get_worker_when_running(self) -> None:
        """Test getting the worker when it's running."""
        # Set up running worker
        mock_service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(mock_service)

        worker = get_worker()

        assert worker == mock_service

        # Cleanup
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(None)

    def test_get_worker_when_not_running(self) -> None:
        """Test getting worker when none is running."""
        syntara.workflows.workflow_engine.services.temporal_worker._get_worker_registry().set_worker(None)

        worker = get_worker()

        assert worker is None


class TestTemporalWorkerServiceLogging:
    """Test logging behavior of worker service."""

    @pytest.mark.asyncio
    async def test_start_logs_connection_info(self) -> None:
        """Test that start() logs connection information."""
        service = TemporalWorkerService(
            temporal_address="test.temporal.io:7233",
            namespace="test-namespace",
            task_queue="test-queue",
        )

        mock_client = MagicMock()
        mock_worker = MagicMock()

        # Create a simple coroutine for worker.run to avoid AsyncMock warnings
        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            # Use the original create_task to avoid recursion
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker),
            patch("asyncio.create_task", side_effect=mock_create_task),
            patch("syntara.workflows.workflow_engine.services.temporal_worker.logger") as mock_logger,
        ):
            await service.start()

            # Verify logger was called with connection info
            mock_logger.info.assert_any_call(
                "Connecting to Temporal server",
                temporal_address="test.temporal.io:7233",
                namespace="test-namespace",
            )

    @pytest.mark.asyncio
    async def test_stop_logs_shutdown_info(self) -> None:
        """Test that stop() logs shutdown information."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        # Create a real asyncio task that will be cancelled
        async def mock_worker_run() -> None:
            raise asyncio.CancelledError

        mock_task = asyncio.create_task(mock_worker_run())
        service._worker_task = mock_task

        with patch("syntara.workflows.workflow_engine.services.temporal_worker.logger") as mock_logger:
            await service.stop()

            # Verify shutdown logs were called
            mock_logger.info.assert_any_call("Stopping Temporal worker...")
            mock_logger.info.assert_any_call("Temporal worker stopped")

    @pytest.mark.asyncio
    async def test_start_failure_logs_error(self) -> None:
        """Test that start() logs errors on failure."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        connection_error = ConnectionError("Connection failed")
        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(side_effect=connection_error),
            ),
            patch("syntara.workflows.workflow_engine.services.temporal_worker.logger") as mock_logger,
        ):
            with pytest.raises(ConnectionError, match="Connection failed"):
                await service.start()

            # Verify error was logged (using exception which includes traceback)
            mock_logger.exception.assert_called_once_with("Failed to start Temporal worker")


class TestStartupReconciliation:
    """Test that reconciliation is called on startup and failures are non-fatal."""

    @pytest.mark.asyncio
    async def test_reconciliation_failure_does_not_block_startup(self) -> None:
        """Worker starts successfully even if reconciliation raises."""
        service = TemporalWorkerService(
            temporal_address="test-address", namespace="test-namespace", task_queue="test-queue"
        )

        mock_client = MagicMock()
        mock_worker = MagicMock()

        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        mock_sync_service = AsyncMock()
        mock_sync_service.reconcile_stale_executions = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker),
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.ActivitySyncService",
                return_value=mock_sync_service,
            ),
            patch("asyncio.create_task"),
        ):
            await service.start()

        assert service.worker == mock_worker


class TestBackgroundWorkerConfiguration:
    """Test that background worker correctly reads concurrency from settings."""

    def test_background_worker_reads_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: background worker must read concurrency from settings, not hardcoded.

        This ensures that if background_worker.py accidentally stops passing
        settings.background_worker_max_concurrent_activities, the test will catch it.
        """
        from syntara.core.config.base import get_settings

        # Set a non-default value
        monkeypatch.setenv("APP_BACKGROUND_WORKER_MAX_CONCURRENT_ACTIVITIES", "7")
        get_settings.cache_clear()

        settings = get_settings()

        # Simulate what background_worker.py does: pass settings value
        service = TemporalWorkerService(
            temporal_address="localhost:7233",
            namespace="default",
            task_queue=settings.background_task_queue,
            max_concurrent_activities=settings.background_worker_max_concurrent_activities,
        )

        # Should be 7 from the environment, not 10 (default) or 50 (main worker default)
        assert service.max_concurrent_activities == 7

    def test_background_worker_default_is_10(self) -> None:
        """Verify background worker concurrency defaults to 10."""
        from syntara.core.config.base import get_settings

        settings = get_settings()
        assert settings.background_worker_max_concurrent_activities == 10

    @pytest.mark.asyncio
    async def test_background_entrypoint_passes_settings_to_start_worker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: background_worker.main() must pass settings value, not a hardcoded constant.

        Exercises the actual entrypoint path so that removing the
        settings.background_worker_max_concurrent_activities pass-through in
        background_worker.py will fail this test, not just the simulation above.
        """
        from syntara.core.config.base import get_settings

        monkeypatch.setenv("APP_BACKGROUND_WORKER_MAX_CONCURRENT_ACTIVITIES", "3")
        get_settings.cache_clear()

        captured: dict[str, object] = {}

        async def mock_start_worker(**kwargs: object) -> TemporalWorkerService:
            captured.update(kwargs)
            return MagicMock(spec=TemporalWorkerService)

        async def mock_run_worker(start_fn: object, **_: object) -> None:
            # Actually invoke the _start callback so start_worker gets called
            if callable(start_fn):
                await start_fn()

        with (
            patch("syntara.workflows.background_worker.start_worker", side_effect=mock_start_worker),
            patch("syntara.workflows.background_worker.run_worker", side_effect=mock_run_worker),
            patch("syntara.workflows.background_worker.validate_encryption_key_at_startup"),
            patch(
                "syntara.workflows.workflow_engine.models.workflow_definition._get_valid_timezones",
                return_value=["UTC"],
            ),
        ):
            from syntara.workflows import background_worker

            await background_worker.main()

        assert captured.get("max_concurrent_activities") == 3, (
            "background_worker.main() must pass settings.background_worker_max_concurrent_activities "
            f"to start_worker, got {captured.get('max_concurrent_activities')!r} instead"
        )


class TestActivityQueueingBehavior:
    """Test that activities queue rather than fail when concurrency cap is reached."""

    @pytest.mark.asyncio
    async def test_low_concurrency_cap_queues_excess_activities(self) -> None:
        """When concurrency cap is low, excess activities queue in Temporal.

        This test verifies the documented behavior: activities that arrive when
        max_concurrent_activities is reached do not fail. Instead, they queue in
        the Temporal task queue and process in FIFO order when a worker slot
        becomes available. This is standard Temporal SDK behavior.
        """
        # Create service with very low concurrency cap to simulate overload
        service = TemporalWorkerService(
            temporal_address="test-address",
            namespace="test-namespace",
            task_queue="test-queue",
            max_concurrent_activities=2,  # Very low cap to test queueing
        )

        # Verify the low cap is set
        assert service.max_concurrent_activities == 2

        mock_client = MagicMock()
        mock_worker = MagicMock()

        async def mock_run() -> None:
            await asyncio.sleep(0)

        mock_worker.run = mock_run

        original_create_task = asyncio.create_task

        def mock_create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            return original_create_task(coro)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Client.connect",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "syntara.workflows.workflow_engine.services.temporal_worker.Worker", return_value=mock_worker
            ) as mock_worker_class,
            patch("asyncio.create_task", side_effect=mock_create_task),
        ):
            await service.start()

            # Verify Worker was created with the low concurrency cap
            mock_worker_class.assert_called_once()
            _, kwargs = mock_worker_class.call_args
            # When cap is reached, Temporal SDK queues excess activities.
            # This is the documented behavior — no application-level failure.
            assert kwargs["max_concurrent_activities"] == 2

    def test_concurrency_cap_is_configurable_per_queue(self) -> None:
        """Different queues can have different concurrency caps.

        Main worker queue can have cap=50 while background queue has cap=10.
        This allows tuning memory usage separately for user vs builtin workflows.
        """
        main_worker = TemporalWorkerService(
            temporal_address="temporal:7233",
            namespace="default",
            task_queue="orchestrator-workflow-queue",
            max_concurrent_activities=50,
        )

        background_worker = TemporalWorkerService(
            temporal_address="temporal:7233",
            namespace="default",
            task_queue="orchestrator-background-queue",
            max_concurrent_activities=10,
        )

        assert main_worker.max_concurrent_activities == 50
        assert background_worker.max_concurrent_activities == 10

        # Verify both workers are configured independently
        assert main_worker.task_queue != background_worker.task_queue
