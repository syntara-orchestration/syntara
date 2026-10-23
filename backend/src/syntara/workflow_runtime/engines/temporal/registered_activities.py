"""Temporal adapter for the neutral activity registry and completion inbox."""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.lib.encryption import SecretEncryptor
from syntara.workflow_runtime.container import ContainerExecutionRequest, ContainerExecutor, OpenShiftContainerExecutor
from syntara.workflow_runtime.contracts import ActivityContext, ActivityError, Completed, Deferred
from syntara.workflow_runtime.models import ActivityCompletion
from syntara.workflow_runtime.registry import ActivityDefinition, ActivityRegistry

logger = structlog.stdlib.get_logger(__name__)
REGISTERED_ACTIVITY = "execute_registered_activity_v1"


class RegisteredActivities:
    """Translate neutral outcomes while keeping all SDK objects in the adapter."""

    def __init__(
        self,
        registry: ActivityRegistry,
        session_factory: async_sessionmaker[AsyncSession],
        encryptor: SecretEncryptor,
        container_executor: ContainerExecutor | None = None,
    ) -> None:
        """Receive handler composition and persistence dependencies."""
        self.registry = registry
        self.session_factory = session_factory
        self.encryptor = encryptor
        self.container_executor = container_executor or OpenShiftContainerExecutor()

    async def _reserve(self, request: dict[str, Any], context: ActivityContext) -> UUID:
        info = activity.info()
        reference = uuid4()
        row = ActivityCompletion(
            id=reference,
            execution_id=context.execution_id,
            project_id=context.project_id,
            node_execution_id=context.node_execution_id,
            activity_name=request["name"],
            activity_version=request["version"],
            engine_workflow_id=info.workflow_id or "",
            engine_run_id=info.workflow_run_id or "",
            attempt=info.attempt,
            encrypted_task_token=self.encryptor.encrypt_field(
                base64.b64encode(info.task_token).decode(), str(reference), "task_token"
            ),
            expires_at=info.started_time + (info.start_to_close_timeout or timedelta(hours=24)),
        )
        async with self.session_factory() as session:
            await session.exec(
                update(ActivityCompletion)
                .where(
                    col(ActivityCompletion.engine_run_id) == row.engine_run_id,
                    col(ActivityCompletion.node_execution_id) == row.node_execution_id,
                    col(ActivityCompletion.attempt) < row.attempt,
                    ActivityCompletion.state.in_(["reserved", "received"]),  # type: ignore[attr-defined]
                )
                .values(state="obsolete")
            )
            await session.exec(insert(ActivityCompletion).values(**row.model_dump()).on_conflict_do_nothing())
            stored = (
                await session.exec(
                    select(ActivityCompletion).where(
                        col(ActivityCompletion.engine_run_id) == row.engine_run_id,
                        col(ActivityCompletion.node_execution_id) == row.node_execution_id,
                        ActivityCompletion.attempt == row.attempt,
                    )
                )
            ).one()
            await session.commit()
            return stored.id

    async def _handoff(self, reference: UUID, outcome: Completed | Deferred | None) -> None:
        async with self.session_factory() as session:
            row = (
                await session.exec(
                    select(ActivityCompletion).where(ActivityCompletion.id == reference).with_for_update()
                )
            ).one()
            if isinstance(outcome, Deferred):
                if row.deferred and row.state in {"delivered", "unconfirmed"}:
                    # A provider can commit its handoff with the request. A fast
                    # decision may then complete the activity before it returns.
                    return
                if row.state not in {"reserved", "received"}:
                    msg = "Activity attempt closed before deferred handoff"
                    raise ActivityError(msg)
                row.deferred = True
                row.external_operation_id = outcome.external_operation_id
            elif row.state in {"reserved", "received"}:
                row.state = "obsolete"
            session.add(row)
            await session.commit()

    async def _run_lifecycle_operation(
        self,
        request: dict[str, Any],
        definition: ActivityDefinition,
        context: ActivityContext,
    ) -> dict[str, Any] | None:
        """Run a lifecycle hook, returning ``None`` for normal execution."""
        operation = request.get("operation", "execute")
        if operation == "execute":
            return None
        if operation not in {"cancel", "expire"}:
            msg = f"Unsupported registered activity operation: {operation}"
            raise ActivityError(msg, code="InvalidActivityOperation")
        outcome = await definition.invoke_lifecycle(operation, request.get("input", {}), context)
        if isinstance(outcome, Deferred):
            msg = f"Lifecycle operation cannot defer: {definition.name}@{definition.version} ({operation})"
            raise ActivityError(msg, code="InvalidActivityLifecycle")
        return {"output": outcome.output}

    @activity.defn(name=REGISTERED_ACTIVITY)
    async def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        """Execute a pinned business handler and interpret its completion mode."""
        reference: UUID | None = None
        try:
            definition = self.registry.resolve(request["name"], request["version"])
            info = activity.info()
            context = ActivityContext(
                execution_id=UUID(request["execution_id"]),
                project_id=UUID(request["project_id"]),
                node_execution_id=info.activity_id,
                idempotency_key=f"{request['execution_id']}:{info.activity_id}",
            )
            lifecycle_result = await self._run_lifecycle_operation(request, definition, context)
            if lifecycle_result is not None:
                return lifecycle_result
            if definition.supports_deferred:
                reference = await self._reserve(request, context)
                context = ActivityContext(
                    context.execution_id,
                    context.project_id,
                    context.node_execution_id,
                    context.idempotency_key,
                    reference,
                )
                activity.heartbeat({"stop_monitor": True})
            if definition.execution_mode == "container":
                outcome = await self.container_executor.run(
                    ContainerExecutionRequest(
                        activity_name=definition.name,
                        activity_version=definition.version,
                        execution_id=context.execution_id,
                        node_execution_id=context.node_execution_id,
                        input=request["input"],
                        image=definition.container_image or "",
                        timeout_seconds=definition.container_timeout_seconds,
                    ),
                    context,
                )
            else:
                outcome = await definition.invoke(request["input"], context)
            outcome = definition.validate_outcome(outcome, context)
            if reference is not None:
                await self._handoff(reference, outcome)
        except ActivityError as exc:
            if reference is not None:
                await self._handoff(reference, None)
            raise ApplicationError(str(exc), type=exc.code, non_retryable=not exc.retryable) from exc
        except (ValueError, KeyError, TypeError) as exc:
            if reference is not None:
                await self._handoff(reference, None)
            raise ApplicationError(str(exc), type="InvalidActivityInput", non_retryable=True) from exc
        if isinstance(outcome, Deferred):
            activity.raise_complete_async()
        return {"output": outcome.output}


class CompletionDelivery:
    """Drain the shared durable inbox independently of the original activity task."""

    def __init__(
        self, client: Client, session_factory: async_sessionmaker[AsyncSession], encryptor: SecretEncryptor
    ) -> None:
        """Use the worker's configured client, including its payload codec."""
        self.client = client
        self.session_factory = session_factory
        self.encryptor = encryptor

    async def deliver_pending(self) -> None:
        """Deliver one bounded batch; row locks allow multiple worker processes."""
        async with self.session_factory() as session:
            rows = (
                await session.exec(
                    select(ActivityCompletion)
                    .where(ActivityCompletion.state == "received", ActivityCompletion.deferred == True)  # noqa: E712
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                if row.expires_at <= datetime.now(UTC):
                    row.state = "obsolete"
                    session.add(row)
                    continue
                token = self.encryptor.decrypt_field(row.encrypted_task_token, str(row.id), "task_token")
                handle = self.client.get_async_activity_handle(task_token=base64.b64decode(token))
                try:
                    if row.failure is not None:
                        await handle.fail(
                            ApplicationError(
                                row.failure["message"],
                                type=row.failure["code"],
                                non_retryable=not row.failure["retryable"],
                            ),
                            rpc_timeout=timedelta(seconds=10),
                        )
                    else:
                        await handle.complete({"output": row.output}, rpc_timeout=timedelta(seconds=10))
                except RPCError as exc:
                    if exc.status == RPCStatusCode.NOT_FOUND:
                        # May be a timed-out attempt OR a successful delivery whose
                        # DB commit was lost. Preserve the outcome without claiming success.
                        row.state = "unconfirmed"
                    else:
                        logger.warning("Runtime completion delivery will retry", completion_ref=str(row.id))
                        continue
                else:
                    row.state = "delivered"
                session.add(row)
            await session.commit()

    async def run(self) -> None:
        """Resume pending delivery after every worker restart."""
        while True:
            try:
                await self.deliver_pending()
            except Exception:
                logger.exception("Runtime completion delivery failed; retrying")
            await asyncio.sleep(2)
