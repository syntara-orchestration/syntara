"""Temporal worker service for workflow execution.

This module provides the Temporal worker that executes workflows and activities.
The worker connects to the Temporal server and processes tasks from configured queues.
"""

import asyncio
import types
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import structlog
from temporalio.client import Client
from temporalio.converter import DataConverter
from temporalio.worker import Worker

from syntara.core.config.base import get_encryption_key, get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.lib.encryption import key_from_string
from syntara.core.tls.temporal import build_temporal_tls_config
from syntara.telemetry.client import flush_telemetry, initialize_telemetry
from syntara.workflows.services.activity_update_publisher import ActivityUpdatePublisher
from syntara.workflows.workflow_engine.activities.registry import ACTIVITY_REGISTRY
from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor
from syntara.workflows.workflow_engine.codecs.credential_codec import CredentialPayloadCodec
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.interceptors.auth_interceptor import WorkflowAuthInterceptor
from syntara.workflows.workflow_engine.interceptors.credential_output_interceptor import CredentialOutputInterceptor
from syntara.workflows.workflow_engine.interceptors.monitoring_interceptor import MonitoringWorkflowInterceptor
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.scheduled_launcher import ScheduledExecutionLauncher, ScheduledWorkflowLauncher
from syntara.workflows.workflow_engine.services.activity_sync_registry import set_activity_sync_service
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService
from syntara.workflows.workflow_engine.workflow_auth import init_signing_key

logger = structlog.stdlib.get_logger(__name__)


class TemporalWorkerService:
    """Service for managing Temporal worker lifecycle."""

    def __init__(
        self,
        temporal_address: str,
        namespace: str,
        task_queue: str,
        activity_registry: dict[ActivityName, Callable[..., Any]] = ACTIVITY_REGISTRY,
        max_cached_workflows: int = 20,
        max_concurrent_workflow_tasks: int = 50,
        max_concurrent_activities: int = 50,
    ) -> None:
        """Initialize Temporal worker service.

        Note:
            For most use cases, use start_worker() factory function instead,
            which provides sensible defaults for temporal_address, namespace, and task_queue.

        Args:
            temporal_address: Temporal server address (host:port)
            namespace: Temporal namespace to use
            task_queue: Task queue name for this worker
            activity_registry: Activity registry to use. Defaults to the full ACTIVITY_REGISTRY.
                Pass BACKGROUND_ACTIVITY_REGISTRY for the background queue worker.
            max_cached_workflows: Maximum workflow states cached in memory for replay.
            max_concurrent_workflow_tasks: Maximum concurrent workflow task executions.
            max_concurrent_activities: Maximum concurrent activity executions. When the limit is
                reached, new activity tasks queue in Temporal and wait for a slot. Standard
                Temporal queuing behavior — no failures, just backpressure.

        """
        self.temporal_address = temporal_address
        self.namespace = namespace
        self._activity_registry = activity_registry
        self.task_queue = task_queue
        self.max_cached_workflows = max_cached_workflows
        self.max_concurrent_workflow_tasks = max_concurrent_workflow_tasks
        self.max_concurrent_activities = max_concurrent_activities
        concurrency = self._build_concurrency_config()
        logger.info("worker_concurrency_configured", **concurrency)
        workflow_thread_pool = self.max_concurrent_workflow_tasks
        activity_thread_pool = self.max_concurrent_activities
        total_thread_pool = workflow_thread_pool + activity_thread_pool
        logger.info("worker_workflow_thread_pool", count=workflow_thread_pool)
        logger.info("worker_activity_thread_pool", count=activity_thread_pool)
        logger.info("worker_total_thread_pool", count=total_thread_pool)
        self.client: Client | None = None
        self.worker: Worker | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self.activity_sync_service: ActivitySyncService | None = None

    def _build_concurrency_config(self) -> dict[str, int]:
        config: dict[str, int] = {}
        config["max_cached_workflows"] = self.max_cached_workflows
        config["max_concurrent_workflow_tasks"] = self.max_concurrent_workflow_tasks
        config["max_concurrent_activities"] = self.max_concurrent_activities
        return config

    async def start(self) -> None:
        """Start the Temporal worker.

        Connects to Temporal server and begins processing workflow tasks.

        Raises:
            Exception: If worker fails to start or connect to Temporal

        """
        try:
            logger.info(
                "Connecting to Temporal server",
                temporal_address=self.temporal_address,
                namespace=self.namespace,
            )

            # Derive the workflow auth HMAC key before the sandbox starts.
            init_signing_key()

            # Encrypt credential payloads in Temporal event history using AES-256-GCM.
            # Uses symmetric encrypt/decrypt (not one-way scrubbing) so workers can
            # still read credential data while it stays encrypted at rest in Temporal.
            encryption_key = key_from_string(get_encryption_key().get_secret_value())
            codec = CredentialPayloadCodec(encryption_key)
            data_converter = DataConverter(payload_codec=codec)
            self.client = await Client.connect(
                self.temporal_address,
                namespace=self.namespace,
                data_converter=data_converter,
                tls=build_temporal_tls_config(),
                interceptors=[WorkflowAuthClientInterceptor()],
            )

            logger.info("Connected to Temporal. Starting worker on queue", task_queue=self.task_queue)

            # Initialize activity publisher for streaming updates
            activity_publisher = ActivityUpdatePublisher()

            # Initialize activity sync service
            self.activity_sync_service = ActivitySyncService(
                temporal_client=self.client,
                session_factory=AsyncSessionLocal,
                activity_publisher=activity_publisher,
            )
            logger.info("Activity sync service initialized")

            # Register in global registry for access by internal activities
            set_activity_sync_service(self.activity_sync_service)

            # Reconcile any executions stuck in non-terminal state from a previous worker crash
            try:
                await self.activity_sync_service.reconcile_stale_executions()
            except Exception:
                logger.exception("Startup reconciliation failed (non-fatal), worker continues")

            # Initialize telemetry (reads installation ID from database)
            await initialize_telemetry()

            scheduled_launcher = ScheduledExecutionLauncher(
                session_factory=AsyncSessionLocal,
                task_queue=self.task_queue,
            )
            activities: list[Callable[..., Any]] = [*self._activity_registry.values(), scheduled_launcher.run]

            # Create worker with workflows, activities, and interceptors
            logger.debug("creating_temporal_worker", task_queue=self.task_queue)
            logger.debug("worker_max_cached_workflows", value=self.max_cached_workflows)
            logger.debug("worker_max_concurrent_workflow_tasks", value=self.max_concurrent_workflow_tasks)
            logger.debug("worker_max_concurrent_activities", value=self.max_concurrent_activities)
            self.worker = Worker(
                self.client,
                task_queue=self.task_queue,
                workflows=[OrchestratorWorkflow, ScheduledWorkflowLauncher],
                activities=activities,
                interceptors=[
                    WorkflowAuthInterceptor(),
                    MonitoringWorkflowInterceptor(),
                    CredentialOutputInterceptor(),
                ],
                max_cached_workflows=self.max_cached_workflows,
                max_concurrent_workflow_tasks=self.max_concurrent_workflow_tasks,
                max_concurrent_activities=self.max_concurrent_activities,
            )

            # Start worker in background task
            self._worker_task = asyncio.create_task(self.worker.run())

            concurrency = self._build_concurrency_config()
            logger.info("temporal_worker_started", task_queue=self.task_queue, **concurrency)

        except Exception:
            logger.exception("Failed to start Temporal worker")
            raise

    async def stop(self) -> None:
        """Stop the Temporal worker gracefully.

        Waits for in-progress tasks to complete before shutting down.
        """
        # Shutdown activity sync service first
        if self.activity_sync_service:
            await self.activity_sync_service.shutdown()
            self.activity_sync_service = None

        # Unregister from global registry
        set_activity_sync_service(None)

        if self._worker_task:
            logger.info("Stopping Temporal worker...")

            # Cancel the worker task
            self._worker_task.cancel()

            try:
                await self._worker_task
            except asyncio.CancelledError:
                logger.info("Worker task cancelled successfully")

            self._worker_task = None

        # Flush pending telemetry events after worker has fully stopped
        flush_telemetry()

        # Client cleanup is handled automatically by Temporal SDK
        self.client = None

        logger.info("Temporal worker stopped")

    async def __aenter__(self) -> "TemporalWorkerService":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        _ = exc_type, exc_val, exc_tb  # Unused but required for __aexit__
        await self.stop()


class WorkerRegistry:
    """Registry for managing TemporalWorkerService lifecycle without global variables."""

    def __init__(self) -> None:
        """Initialize the registry."""
        self._worker: TemporalWorkerService | None = None

    def set_worker(self, worker: TemporalWorkerService | None) -> None:
        """Register the TemporalWorkerService instance.

        Args:
            worker: TemporalWorkerService instance or None

        """
        self._worker = worker

    def get_worker(self) -> TemporalWorkerService | None:
        """Get the registered TemporalWorkerService instance.

        Returns:
            TemporalWorkerService if registered, None otherwise

        """
        return self._worker


@lru_cache(maxsize=1)
def _get_worker_registry() -> WorkerRegistry:
    """Get the singleton WorkerRegistry instance.

    lru_cache provides thread-safe singleton without global mutable state.
    The registry itself manages the mutable worker reference.

    Returns:
        The shared WorkerRegistry instance

    """
    return WorkerRegistry()


async def start_worker(
    temporal_address: str | None = None,
    namespace: str | None = None,
    task_queue: str | None = None,
    activity_registry: dict[ActivityName, Callable[..., Any]] = ACTIVITY_REGISTRY,
    max_concurrent_activities: int | None = None,
) -> TemporalWorkerService:
    """Start the global Temporal worker service.

    This function should be called during application startup.

    Args:
        temporal_address: Temporal server address (default from settings)
        namespace: Temporal namespace (default from settings)
        task_queue: Task queue name (default from settings)
        activity_registry: Activity registry to use (defaults to full ACTIVITY_REGISTRY).
            Pass BACKGROUND_ACTIVITY_REGISTRY for the background queue worker.
        max_concurrent_activities: Override max concurrent activities. Defaults to
            ``settings.max_concurrent_activities``. Background workers should pass
            ``settings.background_worker_max_concurrent_activities``.

    Returns:
        TemporalWorkerService instance

    Example:
        >>> await start_worker()  # Called in app startup

    """
    registry = _get_worker_registry()
    existing_worker = registry.get_worker()

    if existing_worker is not None:
        logger.warning("Temporal worker already running")
        return existing_worker

    settings = get_settings()
    worker_service = TemporalWorkerService(
        temporal_address=temporal_address or settings.temporal_address,
        namespace=namespace or settings.temporal_namespace,
        task_queue=task_queue or settings.task_queue,
        activity_registry=activity_registry,
        max_cached_workflows=settings.max_cached_workflows,
        max_concurrent_workflow_tasks=settings.max_concurrent_workflow_tasks,
        max_concurrent_activities=(
            max_concurrent_activities if max_concurrent_activities is not None else settings.max_concurrent_activities
        ),
    )

    logger.info("temporal_worker_service_created")
    logger.info("starting_temporal_worker", temporal_address=worker_service.temporal_address)
    logger.info("temporal_worker_namespace", namespace=worker_service.namespace)
    logger.info("temporal_worker_task_queue", task_queue=worker_service.task_queue)
    logger.info("temporal_worker_max_cached_workflows", value=worker_service.max_cached_workflows)
    logger.info("temporal_worker_max_concurrent_workflow_tasks", value=worker_service.max_concurrent_workflow_tasks)
    logger.info("temporal_worker_max_concurrent_activities", value=worker_service.max_concurrent_activities)
    logger.info("temporal_worker_config_complete")

    await worker_service.start()
    registry.set_worker(worker_service)

    return worker_service


async def stop_worker() -> None:
    """Stop the global Temporal worker service.

    This function should be called during application shutdown.

    Example:
        >>> await stop_worker()  # Called in app shutdown

    """
    registry = _get_worker_registry()
    worker_service = registry.get_worker()

    if worker_service is None:
        logger.warning("No Temporal worker running")
        return

    await worker_service.stop()
    registry.set_worker(None)


def get_worker() -> TemporalWorkerService | None:
    """Get the current worker service instance.

    Returns:
        TemporalWorkerService if started, None otherwise

    """
    return _get_worker_registry().get_worker()
