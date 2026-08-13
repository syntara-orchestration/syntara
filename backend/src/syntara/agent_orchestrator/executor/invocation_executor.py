"""Service for executing invocations decoupled from creation."""

import asyncio
import contextlib
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import structlog

from syntara.audit.utils import escalate_actor_type
from syntara.core.models.principal import service_principal_id

if TYPE_CHECKING:
    import httpx

    from syntara.agent_orchestrator.context_manager.compressor import CompressorService
    from syntara.workflows.workflow_engine.models.workflow_definition import IntegrationConnectionConfig

from sqlalchemy.orm import selectinload
from sqlmodel import col, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.audit.invocation_lifecycle import InvocationLifecycleEvent
from syntara.agent_orchestrator.clients.openrouter_config import get_openrouter_llm
from syntara.agent_orchestrator.context_manager import ContextManagerPlanner
from syntara.agent_orchestrator.exceptions import (
    CredentialResolutionError,
    InvocationCancelledError,
    LLMConfigurationError,
)
from syntara.agent_orchestrator.models import (
    Invocation,
    InvocationContextData,
    InvocationMetadata,
    InvocationStatus,
    LLMCredentialConfig,
)
from syntara.agent_orchestrator.services.orchestration_service import OrchestrationService
from syntara.agent_orchestrator.token_manager.repository import TokenUsageRepository
from syntara.agent_orchestrator.utils.context_helpers import (
    extract_execution_id,
    extract_request_id,
    extract_workflow_id,
)
from syntara.agent_orchestrator.utils.token_usage import aggregate_token_usage
from syntara.agent_orchestrator.utils.workflow_signal_client import WorkflowSignalClient
from syntara.audit.context_managers import actor_context as audit_actor_context
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import AuditActorContext
from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.models.principal import PrincipalType
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.files.file_manager import FileManager, get_file_manager
from syntara.files.models import FILE_TERMINAL_STATUSES, FileStatus
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import LLMProviderConfiguration
from syntara.integrations.models.llm_model import LLMModel
from syntara.integrations.services.integration_service import ALLOWED_CREDENTIAL_TYPES
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType

logger = structlog.stdlib.get_logger(__name__)

# Polling constants for _wait_for_file_conversions
_CONVERSION_WAIT_TIMEOUT_SECONDS = 310.0
_CONVERSION_WAIT_INITIAL_INTERVAL = 0.5
_CONVERSION_WAIT_MAX_INTERVAL = 5.0
_CONVERSION_WAIT_BACKOFF_FACTOR = 2.0


def _extract_model_name(result_dict: dict[str, Any]) -> str | None:
    """Extract model name from result metadata.

    Args:
        result_dict: Result dictionary from orchestration service

    Returns:
        Model name if found, None otherwise

    """
    if isinstance(result_dict, dict):
        response_metadata = result_dict.get("response_metadata")
        if isinstance(response_metadata, dict):
            return response_metadata.get("model")
    return None


class InvocationExecutor:
    """Service for executing invocations independently of creation.

    This service is designed to be called by background tasks after
    document conversion is complete, allowing for decoupled execution.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncGenerator[AsyncSession, None]] = get_db,
        file_manager_factory: Callable[[], FileManager] = get_file_manager,
        token_usage_repository: TokenUsageRepository | None = None,
    ) -> None:
        """Initialize execution service with database session factory.

        Args:
            session_factory: Factory function for creating database sessions
            file_manager_factory: Factory function for creating FileManager
            token_usage_repository: Optional repository for token usage updates

        """
        self.session_factory = session_factory
        self.file_manager = file_manager_factory()
        self.token_usage_repository = token_usage_repository or TokenUsageRepository()
        # Store the context manager factory (callable that returns a context manager)
        self.get_async_session_context = contextlib.asynccontextmanager(session_factory)

    async def _get_actor_context_for_invocation(self, invocation: Invocation) -> AuditActorContext:
        """Get AuditActorContext for an invocation's creator.

        Args:
            invocation: Invocation being executed

        Returns:
            ActorContext with atomic actor_id and actor_username

        """
        user = await self._load_user_for_actor_context(invocation.created_by)
        if user:
            return AuditActorContext(
                actor_id=user.id,
                actor_username=user.username,
                actor_type=escalate_actor_type(user.id),
            )
        settings = get_settings()
        cn = settings.service_identity
        logger.warning(
            "User associated with Invocation.created_by cannot be found. Using service principal context.",
            invocation_id=invocation.id,
            created_by=invocation.created_by,
        )
        return AuditActorContext(
            actor_id=service_principal_id(cn),
            actor_username=cn,
            actor_type=PrincipalType.SERVICE,
        )

    async def _load_invocation(self, invocation_id: UUID) -> Invocation | None:
        """Load invocation from database.

        Args:
            invocation_id: UUID of invocation to load

        Returns:
            Invocation if found, None otherwise

        """
        async with self.get_async_session_context() as session:
            return await session.get(Invocation, invocation_id)

    async def _load_user_for_actor_context(self, user_id: UUID) -> User | None:
        """Load user from database for actor context.

        Args:
            user_id: UUID of user to load

        Returns:
            User if found, None otherwise

        """
        async with self.get_async_session_context() as session:
            return await session.get(User, user_id)

    async def _update_invocation_status(
        self,
        invocation_id: UUID,
        status: InvocationStatus,
        **fields: Any,  # noqa: ANN401
    ) -> bool:
        """Update invocation status and optional fields atomically.

        Args:
            invocation_id: UUID of invocation to update
            status: New status to set
            **fields: Additional fields to update (started_at, completed_at, result,
                     model_name, error_message, etc.)

        Returns:
            True if update succeeded, otherwise False

        """
        async with self.get_async_session_context() as session:
            # mypy doesn't recognize SQLAlchemy column comparison operators
            stmt = (
                update(Invocation)
                .where(Invocation.id == invocation_id)  # type: ignore[arg-type]
                .where(Invocation.status != InvocationStatus.CANCELLED)  # type: ignore[arg-type]
                .values(status=status, **fields)
            )
            result = await session.exec(stmt)
            await session.commit()
            # Cast to access rowcount (exists on CursorResult at runtime)
            return bool(cast("Any", result).rowcount > 0)

    async def _complete_invocation_if_not_cancelled(
        self,
        invocation_id: UUID,
        **fields: Any,  # noqa: ANN401
    ) -> bool:
        """Update invocation status to COMPLETE only if not currently cancelled.

        Uses a conditional UPDATE to atomically check status and update,
        preventing race condition where cancellation overwrites completion.

        This solves the race condition where:
        1. Executor reads status (RUNNING)
        2. Cancel request commits status=CANCELLED
        3. Executor overwrites with COMPLETED

        The WHERE clause ensures the UPDATE only succeeds if status != CANCELLED.

        Args:
            invocation_id: UUID of invocation to update
            **fields: Additional fields to update (result, model_name, completed_at, etc.)

        Returns:
            True if update succeeded, False if invocation was already cancelled

        """
        async with self.get_async_session_context() as session:
            # mypy doesn't recognize SQLAlchemy column comparison operators
            stmt = (
                update(Invocation)
                .where(Invocation.id == invocation_id)  # type: ignore[arg-type]
                .where(Invocation.status != InvocationStatus.CANCELLED)  # type: ignore[arg-type]
                .values(status=InvocationStatus.COMPLETED, **fields)
            )
            result = await session.exec(stmt)
            await session.commit()
            # Cast to access rowcount (exists on CursorResult at runtime)
            return bool(cast("Any", result).rowcount > 0)

    async def _fail_invocation_if_not_cancelled(
        self,
        invocation_id: UUID,
        **fields: Any,  # noqa: ANN401
    ) -> bool:
        """Update invocation status to FAILED only if not currently cancelled.

        Uses a conditional UPDATE to atomically check status and update,
        preventing race condition where cancellation overwrites completion.

        This solves the race condition where:
        1. Executor reads status (RUNNING)
        2. Cancel request commits status=CANCELLED
        3. Executor overwrites with COMPLETED

        The WHERE clause ensures the UPDATE only succeeds if status != CANCELLED.

        If started_at is not already set, it will be set to the current timestamp.
        This handles the case where an invocation fails before execution begins
        (e.g., LLM configuration errors).

        Args:
            invocation_id: UUID of invocation to update
            **fields: Additional fields to update (result, model_name, completed_at, etc.)
                     If 'started_at' is not in fields, it will be conditionally set
                     using COALESCE (only if currently NULL).

        Returns:
            True if update succeeded, False if invocation was already cancelled

        """
        async with self.get_async_session_context() as session:
            # Load the invocation to check if started_at is None
            invocation = await session.get(Invocation, invocation_id)
            if invocation and invocation.started_at is None and "started_at" not in fields:
                fields["started_at"] = datetime.now(UTC)

            # mypy doesn't recognize SQLAlchemy column comparison operators
            stmt = (
                update(Invocation)
                .where(Invocation.id == invocation_id)  # type: ignore[arg-type]
                .where(Invocation.status != InvocationStatus.CANCELLED)  # type: ignore[arg-type]
                .values(status=InvocationStatus.FAILED, **fields)
            )
            result = await session.exec(stmt)
            await session.commit()
            # Cast to access rowcount (exists on CursorResult at runtime)
            return bool(cast("Any", result).rowcount > 0)

    async def execute_invocation(self, invocation_id: UUID, *, actor_context: AuditActorContext | None = None) -> None:
        """Execute invocation by ID, loading fresh data from database.

        This method loads the invocation from the database to get the latest
        FileMetadata status updates from background tasks.

        Uses short-lived sessions for each database operation to avoid
        holding connections during long-running LLM calls.

        Args:
            invocation_id: UUID of the invocation to execute
            actor_context: Pre-built actor context from the caller. When provided,
                skips the DB lookup in _get_actor_context_for_invocation.

        """
        # Load fresh invocation from database to get latest FileMetadata status
        invocation: Invocation | None = await self._load_invocation(invocation_id)
        if not invocation:
            logger.error("Invocation not found for execution", invocation_id=invocation_id)
            return

        # Check if invocation was cancelled before execution
        if invocation.status == InvocationStatus.CANCELLED:
            logger.info("Invocation was cancelled before execution", invocation_id=invocation_id)
            return

        logger.info(
            "Executing invocation",
            invocation_id=invocation.id,
        )

        # Parse context_data into typed model once, reused throughout execution
        ctx = InvocationContextData.model_validate(invocation.context_data or {})

        # Wait for file conversions to reach terminal state before proceeding
        await self._wait_for_file_conversions(ctx)

        # Log conversion failures but allow execution to proceed (FR-020)
        await self._log_conversion_failures(invocation, ctx)

        # Initialize OrchestrationService - fail immediately if LLM not configured
        init_result = await self._init_orchestration(invocation, ctx)
        if init_result is None:
            return

        orchestration_service, llm_http_client = init_result

        # Execute orchestration with error handling
        workflow_id: UUID | None = extract_workflow_id(ctx)
        activity_id: str | None = ctx.activity_id
        execution_id: UUID | None = extract_execution_id(ctx)
        request_id: UUID | None = extract_request_id(ctx)
        if actor_context is None:
            actor_context = await self._get_actor_context_for_invocation(invocation)
        try:
            with audit_actor_context(
                actor=actor_context,
                workflow_id=workflow_id,
                activity_id=activity_id,
                execution_id=execution_id,
                request_id=request_id,
            ):
                await self._execute_orchestration(invocation, orchestration_service, ctx, actor_context)
        finally:
            if llm_http_client is not None:
                await llm_http_client.aclose()

    async def _execute_orchestration(
        self,
        invocation: Invocation,
        orchestration_service: OrchestrationService,
        ctx: InvocationContextData,
        actor_context: AuditActorContext,
    ) -> None:
        """Execute orchestration service and handle result processing.

        Args:
            invocation: The invocation to execute
            orchestration_service: Initialized orchestration service
            ctx: Parsed context_data model
            actor_context: Actor context for audit event

        """
        recorder = get_metrics_recorder()
        invocation_start = time.perf_counter()
        execution_id = extract_execution_id(ctx)
        request_id = extract_request_id(ctx)

        try:
            # Mark invocation as started
            if await self._update_invocation_status(
                invocation.id,
                InvocationStatus.RUNNING,
                started_at=datetime.now(UTC),
            ):
                # Dispatch RUNNING event
                AuditEventDispatcher.dispatch(
                    InvocationLifecycleEvent(
                        session_id=invocation.session_id,
                        invocation_id=invocation.id,
                        execution_id=execution_id,
                        request_id=request_id,
                        status=InvocationStatus.RUNNING,
                        activity_id=ctx.activity_id,
                        activity_name=ctx.activity_name,
                    )
                )

            # Execute through OrchestrationService (which handles context enhancement internally)
            logger.info(
                "Executing through OrchestrationService",
                invocation_id=invocation.id,
                prompt=invocation.prompt,
            )

            # Extract response_schema for structured output support
            opaque = ctx.metadata.response_schema if ctx.metadata else None
            response_schema = opaque.get_data() if opaque else None

            result_dict = await orchestration_service.execute(
                prompt=invocation.prompt,
                session_id=invocation.session_id,
                invocation_id=invocation.id,
                actor_context=actor_context,
                ctx=ctx,
                execution_id=execution_id,
                response_schema=response_schema,
            )

            # Extract model name from result metadata
            model_name = _extract_model_name(result_dict)

            # Intentional denormalization: trace steps are stored in both result.agent_trace
            # (for the workflow callback signal) and trace_events column (for future indexed
            # queries, e.g. "find all invocations that called tool X").
            agent_trace = result_dict.get("agent_trace")
            trace_events = agent_trace.get("steps") if isinstance(agent_trace, dict) else None

            # Atomically update to COMPLETED only if not already CANCELLED
            # This prevents race condition where cancellation is overwritten
            updated = await self._complete_invocation_if_not_cancelled(
                invocation.id,
                result=result_dict,
                model_name=model_name,
                completed_at=datetime.now(UTC),
                trace_events=trace_events,
            )

            if not updated:
                # Invocation was cancelled during execution - conditional UPDATE failed
                logger.warning(
                    "Invocation was cancelled during execution, completion update skipped",
                    invocation_id=invocation.id,
                )
                # Dispatch CANCELLED event (cancellation service may have already done this)
                AuditEventDispatcher.dispatch(
                    InvocationLifecycleEvent(
                        session_id=invocation.session_id,
                        invocation_id=invocation.id,
                        execution_id=execution_id,
                        request_id=request_id,
                        status=InvocationStatus.CANCELLED,
                        activity_id=ctx.activity_id,
                        activity_name=ctx.activity_name,
                    )
                )
                self._record_invocation_metrics(recorder, invocation_start, invocation.id, status="cancelled")
                return

            # Update token usage record with actual provider-reported counts
            # Only record for successfully completed invocations (not cancelled)
            await self._update_token_usage(result_dict, invocation)

            # Dispatch COMPLETED event
            AuditEventDispatcher.dispatch(
                InvocationLifecycleEvent(
                    session_id=invocation.session_id,
                    invocation_id=invocation.id,
                    execution_id=execution_id,
                    request_id=request_id,
                    status=InvocationStatus.COMPLETED,
                    model_name=model_name,
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )

            self._record_invocation_metrics(recorder, invocation_start, invocation.id, status="success")

        except InvocationCancelledError:
            # Invocation was cancelled during execution - this is expected behavior
            # Don't mark as failed since cancellation is already handled
            logger.info("Invocation cancelled during execution", invocation_id=invocation.id)
            self._record_invocation_metrics(recorder, invocation_start, invocation.id, status="cancelled")
        except Exception as e:
            self._record_invocation_metrics(recorder, invocation_start, invocation.id, status="error", error=e)

            logger.exception(
                "Exception during invocation execution",
                invocation_id=invocation.id,
                error_type=type(e).__name__,
            )

            if await self._fail_invocation_if_not_cancelled(
                invocation.id,
                completed_at=datetime.now(UTC),
                error_message=f"{type(e).__name__}: {e}",
            ):
                # Dispatch FAILED event
                AuditEventDispatcher.dispatch(
                    InvocationLifecycleEvent(
                        session_id=invocation.session_id,
                        invocation_id=invocation.id,
                        execution_id=execution_id,
                        request_id=request_id,
                        status=InvocationStatus.FAILED,
                        error_type=type(e).__name__,
                        activity_id=ctx.activity_id,
                        activity_name=ctx.activity_name,
                    )
                )

            # Send failure signal to workflow
            cb_url = ctx.callback_url.get_secret_value() if ctx.callback_url else None
            await WorkflowSignalClient.send_failure_signal(cb_url, invocation.id, e)

    async def _update_token_usage(
        self,
        result_dict: dict[str, Any],
        invocation: Invocation,
    ) -> None:
        """Update TokenUsageRecord with actual provider-reported token counts.

        Pops llm_token_usage_log from result_dict (so it's not stored in invocation.result),
        aggregates token counts across calls, and updates the record via SAVEPOINT.
        Non-blocking: logs warning on failure but never raises (FR-007).

        Args:
            result_dict: Result dictionary (modified in-place to remove llm_token_usage_log)
            invocation: The Invocation object (provides .id as UUID)

        """
        usage_log = result_dict.pop("llm_token_usage_log", [])
        if not usage_log:
            return

        total_prompt, total_completion, total_tokens, usage_details = aggregate_token_usage(usage_log)

        try:
            async with self.get_async_session_context() as session, session.begin_nested():
                await self.token_usage_repository.update_with_actual_token_usage(
                    invocation_id=invocation.id,
                    prompt_tokens=total_prompt,
                    completion_tokens=total_completion,
                    token_count=total_tokens,
                    usage_details=usage_details,
                    session=session,
                    user_id=invocation.created_by,
                )
            logger.info(
                "Post-LLM token usage updated",
                user_id=str(invocation.created_by),
                invocation_id=str(invocation.id),
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
                token_count=total_tokens,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to update post-LLM token usage (non-blocking)",
                user_id=str(invocation.created_by),
                invocation_id=str(invocation.id),
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
                token_count=total_tokens,
                exc_info=True,
            )

    async def _init_orchestration(
        self, invocation: Invocation, ctx: InvocationContextData
    ) -> "tuple[OrchestrationService, httpx.AsyncClient | None] | None":
        """Initialise LLM and OrchestrationService, handling configuration failures.

        Extracts LLM credentials from invocation context_data (injected by the
        credential system via agentic_activity) and falls back to env vars.

        Returns ``(OrchestrationService, optional httpx client)`` or ``None``
        on failure.  The caller must close the httpx client when orchestration
        completes.
        """
        meta = ctx.metadata

        try:
            logger.info("Initializing LLM for invocation", invocation_id=invocation.id)

            await self._validate_credentials_eagerly(meta, invocation.project_id)

            raw_credential_id = meta.credential_id.get_secret_value() if meta and meta.credential_id else None
            credential_api_key: str | None = None
            if raw_credential_id:
                credential_api_key = await self._resolve_llm_api_key(raw_credential_id)

            resolved_model: str | None = None
            integration_base_url: str | None = None
            provider_hint: str | None = None
            insecure_skip_tls_verify = False
            ca_certificate: str | None = None
            if meta and meta.llm_model_id:
                (
                    resolved_model,
                    integration_base_url,
                    provider_hint,
                    insecure_skip_tls_verify,
                    ca_certificate,
                ) = await self._resolve_llm_model_and_integration(meta.llm_model_id)
            else:
                logger.warning(
                    "No llm_model_id configured, falling back to global LLM settings",
                    invocation_id=invocation.id,
                )

            llm, llm_http_client = await get_openrouter_llm(
                api_key=credential_api_key,
                base_url=integration_base_url,
                model=resolved_model,
                insecure_skip_tls_verify=insecure_skip_tls_verify,
                ca_certificate=ca_certificate,
            )

            llm_credential_config = LLMCredentialConfig(
                api_key=credential_api_key or "",
                base_url=str(llm.openai_api_base or ""),
                model=llm.model_name,
                provider_hint=provider_hint,
                insecure_skip_tls_verify=insecure_skip_tls_verify,
                ca_certificate=ca_certificate,
            )

            # Pass the credential-configured LLM to the compressor so it doesn't
            # create its own (which would fail without env var).
            def compressor_factory() -> "CompressorService":
                from syntara.agent_orchestrator.context_manager.compressor import CompressorService  # noqa: PLC0415

                return CompressorService(llm=llm)

            context_manager_planner = ContextManagerPlanner(
                session_factory=self.session_factory,
                compressor_service_factory=compressor_factory,
                llm_credential_config=llm_credential_config,
            )
            service = OrchestrationService(
                llm=llm,
                context_manager_planner=context_manager_planner,
                credential_resolver=self._make_mcp_credential_resolver(meta.integration_connections if meta else None),
                tool_selection_strategy=(meta.tool_selection_strategy if meta else None) or "NONE",
                tool_selections=list(meta.tool_selections) if meta else [],
            )
            logger.info("LLM initialized successfully for invocation", invocation_id=invocation.id)
            return service, llm_http_client
        except (LLMConfigurationError, CredentialResolutionError) as e:
            logger.exception("LLM configuration failed for invocation", invocation_id=invocation.id)
            now = datetime.now(UTC)
            await self._update_invocation_status(
                invocation.id,
                InvocationStatus.FAILED,
                started_at=now,
                error_message=type(e).__name__,
                completed_at=now,
            )
            logger.exception("Invocation failed", invocation_id=invocation.id, error_message=str(e))

            cb_url = ctx.callback_url.get_secret_value() if ctx.callback_url else None
            await WorkflowSignalClient.send_failure_signal(cb_url, invocation.id, e)
            return None

    @staticmethod
    def _record_invocation_metrics(
        recorder: MetricsRecorder,
        start_time: float,
        invocation_id: UUID,
        *,
        status: str,
        error: Exception | None = None,
    ) -> None:
        """Record invocation duration and status metrics.

        Args:
            recorder: Metrics recorder instance.
            start_time: ``time.perf_counter()`` value captured at invocation start.
            invocation_id: Invocation UUID.
            status: Outcome label (``"success"``, ``"error"``, or ``"cancelled"``).
            error: Optional exception for error-path labels.

        """
        duration_ms = (time.perf_counter() - start_time) * 1000
        labels: dict[str, str] = {"invocation_id": str(invocation_id), "status": status}
        recorder.record(MetricType.AGENT_INVOCATION_DURATION, duration_ms, unit="ms", labels=labels)

        status_labels = dict(labels)
        if error is not None:
            status_labels["error_type"] = type(error).__name__
        recorder.record(MetricType.AGENT_STATUS, value=1, labels=status_labels)

    async def _log_conversion_failures(self, invocation: Invocation, ctx: InvocationContextData) -> None:
        """Log conversion failures but allow execution to proceed (FR-020).

        Queries FileMetadata records by file_ids via FileManager and logs any
        that have CONVERSION_FAILED status. This allows execution to continue
        with partial file context rather than failing entirely.

        Args:
            invocation: The invocation to check for conversion failures
            ctx: Parsed context_data model

        """
        if not ctx.file_ids:
            return

        # Convert strings to UUIDs at the boundary
        file_ids = [UUID(fid) for fid in ctx.file_ids]

        # Create session for DB operations
        async with self.get_async_session_context() as session:
            # Query FileMetadata records via FileManager
            file_metadata_records = await self.file_manager.get_files_metadata(file_ids, session)
            failed_files = [f for f in file_metadata_records if f.status == FileStatus.CONVERSION_FAILED]

            if failed_files:
                logger.warning(
                    "Proceeding with invocation despite failed conversions",
                    failed_conversion_count=len(failed_files),
                    invocation_id=invocation.id,
                    failed_files=[f.filename for f in failed_files],
                )

    async def _validate_credentials_eagerly(
        self,
        meta: InvocationMetadata | None,
        project_id: UUID,
    ) -> None:
        """Validate all referenced credentials before execution starts.

        Checks existence, enabled, project membership, credential type, and
        secret data for both the LLM credential and MCP integration credentials.

        Raises:
            CredentialResolutionError: On first validation failure.

        """
        if meta is None:
            return
        expected = self._collect_expected_credentials(meta)
        if not expected:
            return

        cred_uuids = self._parse_credential_uuids(expected)
        found = await self._load_credentials_batch(cred_uuids)

        for (cred_id_str, allowed_types), cred_uuid in zip(expected, cred_uuids, strict=True):
            self._check_credential(found.get(cred_uuid), cred_id_str, allowed_types, project_id)

    @staticmethod
    def _collect_expected_credentials(meta: InvocationMetadata) -> list[tuple[str, frozenset[str]]]:
        expected: list[tuple[str, frozenset[str]]] = []
        if meta.credential_id:
            # credential_id is a UUID wrapped in SecretStr to suppress logging —
            # get_secret_value() just unwraps it, no decryption or secret fetch.
            expected.append(
                (
                    meta.credential_id.get_secret_value(),
                    ALLOWED_CREDENTIAL_TYPES[IntegrationType.LLM_PROVIDER],
                )
            )
        expected.extend(
            (conn.credential_id, ALLOWED_CREDENTIAL_TYPES[IntegrationType.MCP_SERVER])
            for conn in (meta.integration_connections or [])
        )
        return expected

    @staticmethod
    def _parse_credential_uuids(expected: list[tuple[str, frozenset[str]]]) -> list[UUID]:
        uuids: list[UUID] = []
        for cred_id_str, _ in expected:
            try:
                uuids.append(UUID(cred_id_str))
            except ValueError as e:
                msg = f"Invalid credential ID '{cred_id_str}'."
                raise CredentialResolutionError(msg) from e
        return uuids

    async def _load_credentials_batch(self, cred_uuids: list[UUID]) -> dict[UUID, Credential]:
        async with self.get_async_session_context() as session:
            result = await session.exec(
                select(Credential)
                .where(col(Credential.id).in_(cred_uuids))
                .options(selectinload(Credential.credential_type))  # type: ignore[arg-type]
            )
            return {cred.id: cred for cred in result.all()}

    @staticmethod
    def _check_credential(
        credential: Credential | None,
        cred_id_str: str,
        allowed_types: frozenset[str],
        project_id: UUID,
    ) -> None:
        if not credential:
            msg = f"Credential '{cred_id_str}' not found."
            raise CredentialResolutionError(msg)
        if credential.project_id != project_id:
            msg = "Credential does not belong to this project."
            raise CredentialResolutionError(msg)
        if not credential.enabled:
            msg = f"Credential '{credential.name}' is disabled."
            raise CredentialResolutionError(msg)
        actual = credential.credential_type.name if credential.credential_type else None
        if not actual or actual not in allowed_types:
            expected = sorted(allowed_types)
            msg = f"Credential '{credential.name}' has type '{actual or 'unknown'}', expected one of {expected}."
            raise CredentialResolutionError(msg)
        if not credential.secret_id:
            msg = f"Credential '{credential.name}' has no stored secret data."
            raise CredentialResolutionError(msg)

    async def _wait_for_file_conversions(self, ctx: InvocationContextData) -> None:
        """Wait for all file conversions to reach a terminal state.

        Polls FileMetadata statuses with exponential backoff until all files
        are CONVERTED or CONVERSION_FAILED. On timeout, proceeds gracefully
        to let downstream code handle the partial state.

        Args:
            ctx: Parsed context_data model containing file_ids

        """
        if not ctx.file_ids:
            return

        file_ids = [UUID(fid) for fid in ctx.file_ids]
        start = time.monotonic()
        interval = _CONVERSION_WAIT_INITIAL_INTERVAL

        while True:
            async with self.get_async_session_context() as session:
                records = await self.file_manager.get_files_metadata(file_ids, session)
                pending = [r for r in records if r.status not in FILE_TERMINAL_STATUSES]

            if not pending:
                logger.info(
                    "All file conversions reached terminal state",
                    file_count=len(file_ids),
                    elapsed=round(time.monotonic() - start, 1),
                )
                return

            elapsed = time.monotonic() - start
            if elapsed >= _CONVERSION_WAIT_TIMEOUT_SECONDS:
                logger.warning(
                    "Timed out waiting for file conversions, proceeding with partial context",
                    file_count=len(file_ids),
                    pending_count=len(pending),
                    pending_files=[(str(r.id), r.status.value) for r in pending],
                    timeout=_CONVERSION_WAIT_TIMEOUT_SECONDS,
                )
                return

            logger.debug(
                "Waiting for file conversions",
                pending_count=len(pending),
                file_count=len(file_ids),
                next_poll_seconds=interval,
            )
            await asyncio.sleep(interval)
            interval = min(interval * _CONVERSION_WAIT_BACKOFF_FACTOR, _CONVERSION_WAIT_MAX_INTERVAL)

    def _make_mcp_credential_resolver(
        self,
        integration_connections: "list[IntegrationConnectionConfig] | None" = None,
    ) -> Callable[[UUID], Awaitable[str | None]]:
        """Return an async callable that resolves the bearer token for an MCP integration.

        When integration_connections is provided, integrations listed there use the
        supplied execution credential. Unlisted integrations return None
        (unauthenticated). The management credential is never used during
        workflow execution — it is reserved for tool discovery and health checks.

        The callable opens a short-lived DB session per call — matching the same
        pattern as _resolve_llm_api_key — so the token is never stored on self.
        """
        # Build lookup: integration_id str → execution credential_id str
        execution_cred_map: dict[str, str] = {
            conn.integration_id: conn.credential_id for conn in (integration_connections or [])
        }

        async def resolver(integration_id: UUID) -> str | None:
            exec_cred_id = execution_cred_map.get(str(integration_id))
            if exec_cred_id:
                logger.debug(
                    "Resolving execution credential for integration",
                    integration_id=str(integration_id),
                    credential_id=exec_cred_id,
                )
                return await self._resolve_mcp_execution_credential(exec_cred_id)
            # No execution credential configured — treat as unauthenticated.
            # The management credential is reserved for tool discovery and health
            # checks only; it must never be used during workflow execution.
            logger.debug("No execution credential configured for integration", integration_id=str(integration_id))
            return None

        return resolver

    async def _resolve_credential(
        self,
        credential_id: str,
        *,
        error_class: type[Exception],
        field_name: str,
        label: str,
        decrypt_hint: str = "",
    ) -> str | None:
        """Resolve a credential value by looking up, decrypting, and extracting a field.

        Handles the common flow shared by MCP execution credentials and LLM API
        keys: parse UUID, open session, fetch Credential, check exists/enabled/has
        secret, decrypt secret, fetch CredentialType, resolve injectors, and
        extract a named value from ``extra_vars``.

        Args:
            credential_id: UUID string of the Credential record.
            error_class: Exception class to raise on any failure.
            field_name: Key to extract from resolved ``extra_vars``.
            label: Human-readable label for error messages (e.g. "execution credential").
            decrypt_hint: Optional hint appended to the decrypt-failure message.

        Returns:
            The extracted value, or ``None`` if the field is absent in extra_vars.

        Raises:
            error_class: If the credential cannot be found, decrypted, or resolved.

        """
        # Sentence-start form of the label for messages that begin with it.
        cap_label = f"{label[0].upper()}{label[1:]}"

        try:
            cred_uuid = UUID(credential_id)
        except ValueError as e:
            msg = f"Invalid {label} ID '{credential_id}'."
            logger.debug("Credential resolution failed: invalid UUID", credential_id=credential_id)
            raise error_class(msg) from e

        async with self.get_async_session_context() as session:
            credential = await session.get(Credential, cred_uuid)
            if not credential:
                msg = f"{cap_label} '{credential_id}' not found."
                logger.debug("Credential resolution failed: not found", credential_id=credential_id)
                raise error_class(msg)
            if not credential.enabled:
                msg = f"{cap_label} '{credential_id}' is disabled."
                logger.debug("Credential resolution failed: disabled", credential_id=credential_id)
                raise error_class(msg)
            if not credential.secret_id:
                msg = f"{cap_label} '{credential_id}' has no stored secret data."
                logger.debug("Credential resolution failed: no secret data", credential_id=credential_id)
                raise error_class(msg)

            try:
                secret_service = create_secret_service(session)
                decrypted = await secret_service.retrieve_secret(credential.secret_id)
            except Exception as e:
                msg = f"Failed to decrypt {label} '{credential_id}'.{decrypt_hint}"
                logger.debug("Credential resolution failed: decryption error", credential_id=credential_id)
                raise error_class(msg) from e

            cred_type = await session.get(CredentialType, credential.credential_type_id)
            if not cred_type:
                msg = f"Credential type for {label} '{credential_id}' not found."
                logger.debug("Credential resolution failed: credential type not found", credential_id=credential_id)
                raise error_class(msg)

            try:
                resolved = InjectorResolver.resolve(cred_type.injectors, decrypted)
            except Exception as e:
                msg = f"Failed to resolve {label} '{credential_id}' injector templates."
                logger.debug("Credential resolution failed: injector error", credential_id=credential_id)
                raise error_class(msg) from e

            logger.debug("Credential resolved", credential_id=credential_id, label=label)
            return resolved.extra_vars.get(field_name)

    async def _resolve_mcp_execution_credential(self, credential_id: str) -> str | None:
        """Resolve the bearer token from a Nexus execution credential for MCP tool calls.

        Returns None when the credential resolves without a bearer_token
        (unauthenticated path).

        Raises:
            CredentialResolutionError: If the credential cannot be found, decrypted, or resolved.

        """
        return await self._resolve_credential(
            credential_id,
            error_class=CredentialResolutionError,
            field_name="bearer_token",
            label="execution credential",
        )

    async def _resolve_llm_model_and_integration(
        self, llm_model_id: str
    ) -> tuple[str, str | None, str | None, bool, str | None]:
        """Resolve an LLM model UUID to (model_id, base_url, provider_hint, insecure_skip_tls_verify, ca_certificate).

        Fetches the LLMModel record and its parent Integration in one DB session,
        eliminating a second connection checkout and the TOCTOU window between them.

        Args:
            llm_model_id: UUID string of the LLMModel record.

        Returns:
            Tuple of (provider model_id, base_url, provider_hint, insecure_skip_tls_verify, ca_certificate).

        Raises:
            LLMConfigurationError: If the model or integration is not found, disabled, or misconfigured.

        """
        try:
            model_uuid = UUID(llm_model_id)
        except ValueError as e:
            msg = f"Invalid LLM model ID '{llm_model_id}'."
            raise LLMConfigurationError(msg) from e

        async with self.get_async_session_context() as session:
            model = await session.get(LLMModel, model_uuid)
            if not model:
                msg = f"LLM model '{llm_model_id}' not found."
                raise LLMConfigurationError(msg)
            if not model.enabled:
                msg = f"LLM model '{llm_model_id}' is disabled."
                raise LLMConfigurationError(msg)

            integration = await session.get(Integration, model.integration_id)
            integration_id = str(model.integration_id)
            if not integration:
                msg = f"LLM provider integration '{integration_id}' not found."
                raise LLMConfigurationError(msg)
            if not integration.enabled:
                msg = f"LLM provider integration '{integration_id}' is disabled."
                raise LLMConfigurationError(msg)
            if not isinstance(integration.configuration, LLMProviderConfiguration):
                msg = f"Integration '{integration_id}' is not an LLM provider."
                raise LLMConfigurationError(msg)

            config = integration.configuration
            # Re-run the integration SSRF policy at request time: the stored base_url may
            # have been re-pointed to a private/metadata address (DNS rebinding) since write
            # time. No-op when base_url is unset (provider default endpoint).
            try:
                validate_integration_configuration_no_ssrf(config)
            except ValueError as e:
                msg = f"LLM provider integration '{integration_id}' base_url is not permitted by SSRF policy."
                raise LLMConfigurationError(msg) from e
            base_url = str(config.base_url) if config.base_url else None
            provider_hint = config.provider_hint.value if config.provider_hint else None
            logger.debug(
                "Resolved LLM model and integration",
                llm_model_id=llm_model_id,
                model_id=model.model_id,
                integration_id=integration_id,
                provider_hint=provider_hint,
            )
            return model.model_id, base_url, provider_hint, config.insecure_skip_tls_verify, config.ca_certificate

    async def _resolve_llm_api_key(self, credential_id: str) -> str:
        """Decrypt LLM API key from credential at execution time.

        Delegates to :meth:`_resolve_credential` for the common lookup/decrypt
        flow, then validates that the resolved key is non-empty.

        Raises:
            LLMConfigurationError: If the credential is not found, disabled, or has no API key.

        """
        api_key = await self._resolve_credential(
            credential_id,
            error_class=LLMConfigurationError,
            field_name="llm_api_key",
            label="LLM credential",
            decrypt_hint=" It may need to be re-saved after key rotation.",
        )
        if not api_key:
            msg = f"LLM credential '{credential_id}' resolved but contains no API key."
            raise LLMConfigurationError(msg)
        return api_key


# ===================================================
# Factory function for dependency injection
# ---------------------------------------------------


def get_invocation_executor(
    session_factory: Callable[[], AsyncGenerator[AsyncSession, None]] = get_db,
) -> InvocationExecutor:
    """Create a InvocationExecutor instance with fresh dependencies.

    Args:
        session_factory: Session factory for database operations (defaults to get_db)

    Returns:
        InvocationExecutor: Fresh InvocationExecutor instance

    Example:
        invocation_executor = get_invocation_executor()
        await invocation_executor.execute_invocation(invocation_id)

    """
    return InvocationExecutor(session_factory=session_factory)


# ===================================================
