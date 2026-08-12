"""Context Manager Planner orchestration.

Main orchestrator for the Context Manager that coordinates retrieval,
compression, and assembly phases to produce final context packages.
"""

import contextlib
import time
from collections.abc import AsyncGenerator, Callable
from typing import NamedTuple
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.audit.context_planning import (
    CancellationEvent,
    ContextPlanningEvent,
    ContextPlanningPhase,
    ContextPlanningStatus,
)
from syntara.agent_orchestrator.exceptions import InvocationCancelledError
from syntara.agent_orchestrator.models import Invocation, InvocationStatus, LLMCredentialConfig
from syntara.agent_orchestrator.token_manager import TokenValidationService
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.database.session import get_db
from syntara.settings.cache.settings_cache import get_runtime_settings

from .assembler_service import AssemblerService
from .compressor import CompressorService
from .model_profile_service import ModelProfileService
from .models import ContextPackage
from .retriever_service.services import RetrieverService, get_retriever_service

logger = structlog.stdlib.get_logger(__name__)


class _PlanningContext(NamedTuple):
    """Immutable bundle of identifiers shared across planning call sites."""

    session_id: str
    invocation_id: UUID
    execution_id: UUID | None
    request_id: UUID | None
    activity_id: str | None
    activity_name: str | None


class ContextManagerPlanner:
    """Main planner that orchestrates context management workflow.

    Coordinates the retrieve → compress → assemble sequence and
    handles errors gracefully.
    """

    def __init__(
        self,
        *,
        compressor_service_factory: Callable[[], CompressorService],
        session_factory: Callable[[], AsyncGenerator[AsyncSession, None]] = get_db,
        retriever_service_factory: Callable[
            [Callable[[], AsyncGenerator[AsyncSession, None]]], RetrieverService
        ] = get_retriever_service,
        llm_credential_config: LLMCredentialConfig | None = None,
    ) -> None:
        """Initialize the context manager planner.

        Args:
            compressor_service_factory: Factory function for creating CompressorService (required)
            session_factory: Session factory for cancellation checks. Defaults to get_db.
            retriever_service_factory: Factory function for creating RetrieverService
            llm_credential_config: Credential config for downstream LLM services (relevancy checker)

        """
        self.settings = get_runtime_settings()
        self.session_factory = session_factory
        self.get_async_session_context = contextlib.asynccontextmanager(session_factory)
        self.retriever_service_factory = retriever_service_factory
        self.compressor_service_factory = compressor_service_factory
        self.llm_credential_config = llm_credential_config

    async def _check_cancellation(
        self,
        session_id: str,
        invocation_id: UUID,
        phase: ContextPlanningPhase,
        execution_id: UUID | None = None,
        request_id: UUID | None = None,
        activity_id: str | None = None,
        activity_name: str | None = None,
    ) -> None:
        """Check if invocation has been cancelled.

        Args:
            session_id: Session identifier for multi-tenant isolation
            invocation_id: UUID of the invocation to check
            phase: Current execution phase for error reporting
            execution_id: Optional Workflow Execution ID
            request_id: Optional X-Request-Id from the originating HTTP request.
            activity_id: Optional workflow activity ID for audit correlation
            activity_name: Optional workflow activity name for audit resource naming

        Raises:
            InvocationCancelledError: If invocation has been cancelled

        """
        try:
            # Create a short-lived session for the cancellation check
            async with self.get_async_session_context() as session:
                invocation = await session.get(Invocation, invocation_id)
                if invocation and invocation.status == InvocationStatus.CANCELLED:
                    logger.info("Invocation cancelled during phase", phase=phase, invocation_id=invocation_id)

                    # Emit cancellation detected event
                    AuditEventDispatcher.dispatch(
                        CancellationEvent(
                            phase=phase,
                            session_id=session_id,
                            invocation_id=invocation_id,
                            execution_id=execution_id,
                            request_id=request_id,
                            activity_id=activity_id,
                            activity_name=activity_name,
                        )
                    )

                    raise InvocationCancelledError(str(invocation_id), phase.value)
        except (SQLAlchemyError, OSError) as e:
            # Log but don't fail on database errors - graceful degradation
            logger.warning(
                "Failed to check cancellation status for invocation, continuing execution",
                invocation_id=invocation_id,
                error=str(e),
                exc_info=True,
            )

    async def _resolve_token_budget(self) -> int:
        """Resolve the token budget from the model profile or fallback settings."""
        try:
            profile_service = ModelProfileService()
            model_name = self.llm_credential_config.model if self.llm_credential_config else None
            provider_hint = self.llm_credential_config.provider_hint if self.llm_credential_config else None
            output_reserve = await self.settings.get_int("context_manager.output_token_reserve")
            safety_margin = await self.settings.get_float("context_manager.tokenizer_safety_margin")

            budget = await profile_service.get_token_budget(
                model=model_name,
                provider_hint=provider_hint,
                output_reserve=output_reserve,
                safety_margin=safety_margin,
            )

            if budget.source == "fallback":
                max_tokens = await self.settings.get_int("context_manager.max_total_tokens")
            else:
                max_tokens = budget.effective_context_budget

            logger.info(
                "Token budget resolved",
                max_tokens=max_tokens,
                source=budget.source,
                model=model_name,
                max_input_tokens=budget.max_input_tokens,
            )
            return max_tokens
        except Exception:  # noqa: BLE001
            max_tokens = await self.settings.get_int("context_manager.max_total_tokens")
            logger.warning(
                "Model-aware budget resolution failed, falling back to max_total_tokens",
                max_tokens=max_tokens,
                exc_info=True,
            )
            return max_tokens

    async def plan_request(
        self,
        session_id: str,
        query: str,
        invocation_id: UUID,
        execution_id: UUID | None = None,
        request_id: UUID | None = None,
        user_id: UUID | None = None,
        activity_id: str | None = None,
        activity_name: str | None = None,
    ) -> ContextPackage:
        """Plan and execute a context request.

        Orchestrates the full context management workflow:
        1. Retrieval: Find relevant documents
        2. Assembly: Create final context package (with internal compression retry loop)

        Args:
            session_id: Session identifier for multi-tenant isolation
            query: User query string for context retrieval
            invocation_id: Invocation ID for cancellation checking
            execution_id: Optional Workflow Execution ID
            request_id: Optional X-Request-Id from the originating HTTP request.
            user_id: Optional UUID of the user making the request (for context assembly)
            activity_id: Optional workflow activity ID for audit correlation
            activity_name: Optional workflow activity name for audit resource naming

        Returns:
            ContextPackage: Assembled context ready for LLM consumption

        Raises:
            InvocationCancelledError: If invocation has been cancelled

        """
        start_time = time.time()

        logger.info("Starting context planning")
        logger.debug("Context planning", tenant=session_id, query=query)

        # Bundle the identifiers that every cancellation check and audit
        # dispatch in this method needs so they are stated once.
        ctx = _PlanningContext(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            activity_id=activity_id,
            activity_name=activity_name,
        )

        # Initialize timing metadata
        timing_data = {}

        # Phase 1: Retrieval
        # Check for cancellation before starting retrieval
        await self._check_cancellation(
            ctx.session_id,
            ctx.invocation_id,
            ContextPlanningPhase.RETRIEVAL,
            execution_id=ctx.execution_id,
            request_id=ctx.request_id,
            activity_id=ctx.activity_id,
            activity_name=ctx.activity_name,
        )

        # Emit STARTED event for retrieval phase
        AuditEventDispatcher.dispatch(
            ContextPlanningEvent(
                phase=ContextPlanningPhase.RETRIEVAL,
                status=ContextPlanningStatus.STARTED,
                session_id=ctx.session_id,
                invocation_id=ctx.invocation_id,
                execution_id=ctx.execution_id,
                request_id=ctx.request_id,
                activity_id=ctx.activity_id,
                activity_name=ctx.activity_name,
            )
        )

        retrieved_docs = []
        retrieval_start = time.time()
        try:
            retriever = self.retriever_service_factory(self.session_factory)
            retrieved_docs = await retriever.retrieve_relevant_documents(
                invocation_id, query, llm_credential_config=self.llm_credential_config
            )
            timing_data["retrieval_time_ms"] = int((time.time() - retrieval_start) * 1000)
            logger.info(
                "Retrieval phase completed",
                retrieval_time_ms=timing_data["retrieval_time_ms"],
                document_count=len(retrieved_docs),
            )

            # Emit COMPLETED event for retrieval phase
            AuditEventDispatcher.dispatch(
                ContextPlanningEvent(
                    phase=ContextPlanningPhase.RETRIEVAL,
                    status=ContextPlanningStatus.COMPLETED,
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    document_count=len(retrieved_docs),
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
        except Exception as e:
            timing_data["retrieval_time_ms"] = int((time.time() - retrieval_start) * 1000)
            logger.exception("Retrieval phase failed")

            # Emit FAILED event for retrieval phase
            AuditEventDispatcher.dispatch(
                ContextPlanningEvent(
                    phase=ContextPlanningPhase.RETRIEVAL,
                    status=ContextPlanningStatus.FAILED,
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    error_type=type(e).__name__,
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            retrieved_docs = []

        # Phase 2: Assembly
        # Check for cancellation before starting assembly
        await self._check_cancellation(
            ctx.session_id,
            ctx.invocation_id,
            ContextPlanningPhase.ASSEMBLY,
            execution_id=ctx.execution_id,
            request_id=ctx.request_id,
            activity_id=ctx.activity_id,
            activity_name=ctx.activity_name,
        )

        # Emit STARTED event for assembly phase
        AuditEventDispatcher.dispatch(
            ContextPlanningEvent(
                phase=ContextPlanningPhase.ASSEMBLY,
                status=ContextPlanningStatus.STARTED,
                session_id=ctx.session_id,
                invocation_id=ctx.invocation_id,
                execution_id=ctx.execution_id,
                request_id=ctx.request_id,
                document_count=len(retrieved_docs),
                activity_id=ctx.activity_id,
                activity_name=ctx.activity_name,
            )
        )

        assembly_start = time.time()
        try:
            # Get configuration parameters from runtime settings
            compression_loop = await self.settings.get_int("context_manager.compression_loop")
            max_tokens = await self._resolve_token_budget()

            # Create assembler with injected dependencies
            token_service = TokenValidationService()
            compressor_service = self.compressor_service_factory()
            assembler = AssemblerService(
                token_service=token_service,
                compressor_service=compressor_service,
            )

            # Assemble context package (with internal compression retry loop)
            # Pass session_factory instead of session - assembler will create
            # short-lived sessions for token validation only
            context_package = await assembler.assemble(
                documents=retrieved_docs,
                max_tokens=max_tokens,
                compression_loop=compression_loop,
                invocation_id=invocation_id,
                user_id=user_id,
                session_factory=self.session_factory,
            )

            timing_data["assembly_time_ms"] = int((time.time() - assembly_start) * 1000)
            logger.info("Assembly phase completed", assembly_time_ms=timing_data["assembly_time_ms"])

            # Emit COMPLETED event for assembly phase
            AuditEventDispatcher.dispatch(
                ContextPlanningEvent(
                    phase=ContextPlanningPhase.ASSEMBLY,
                    status=ContextPlanningStatus.COMPLETED,
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )

        except Exception as e:
            timing_data["assembly_time_ms"] = int((time.time() - assembly_start) * 1000)
            logger.exception("Assembly phase failed")

            # Emit FAILED event for assembly phase
            AuditEventDispatcher.dispatch(
                ContextPlanningEvent(
                    phase=ContextPlanningPhase.ASSEMBLY,
                    status=ContextPlanningStatus.FAILED,
                    session_id=ctx.session_id,
                    invocation_id=ctx.invocation_id,
                    execution_id=ctx.execution_id,
                    request_id=ctx.request_id,
                    error_type=type(e).__name__,
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            raise

        # Calculate total execution time
        total_time_ms = int((time.time() - start_time) * 1000)
        timing_data["total_time_ms"] = total_time_ms

        logger.info("Context planning completed", total_time_ms=total_time_ms)
        logger.debug(
            "Context Package created", package_id=context_package.id, grounding_score=context_package.grounding_score
        )

        return context_package
