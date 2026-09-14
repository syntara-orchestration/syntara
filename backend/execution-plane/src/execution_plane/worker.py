"""Execution Plane TE worker — polls work_items and dispatches to Temporal on completion."""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from execution_plane.models.work_item import WorkItem, WorkItemStatus

logger = structlog.stdlib.get_logger(__name__)

POLL_INTERVAL_SECONDS = 5


async def _claim_pending_items(session: AsyncSession) -> list[WorkItem]:
    """SELECT ... FOR UPDATE SKIP LOCKED to claim pending work items."""
    result = await session.execute(
        select(WorkItem)
        .where(WorkItem.status == WorkItemStatus.PENDING)
        .order_by(WorkItem.created_at)
        .limit(10)
        .with_for_update(skip_locked=True)
    )
    items = list(result.scalars().all())
    for item in items:
        item.status = WorkItemStatus.CLAIMED
        item.claimed_at = datetime.now(UTC)
    if items:
        await session.commit()
    return items


async def _execute_work_item(item: WorkItem, temporal_client: object) -> None:
    """Run the script from the work item payload and complete the Temporal activity."""
    wi_id = str(item.id)
    try:
        from syntara.workflows.workflow_engine.activities.script_activity import (  # noqa: PLC0415
            _execute_script_common,
            _enforce_payload_limit,
            _get_cgroup_memory_limit,
            _prepend_memory_limit,
            ScriptExecutionError,
        )
        from syntara.workflows.workflow_engine.models.workflow_definition import (  # noqa: PLC0415
            ScriptExecutorParameters,
            ScriptOutput,
        )
        from syntara.workflows.workflow_engine import constants  # noqa: PLC0415
        import json  # noqa: PLC0415
        import contextlib  # noqa: PLC0415
        import sys  # noqa: PLC0415

        payload = item.payload
        input_config: dict = payload.get("input_config", {})
        output_config: dict | None = payload.get("output_config")

        config = ScriptExecutorParameters.model_validate(input_config)
        language = config.language.value
        code = config.code
        environment = dict(config.environment)

        timeout = int(input_config.get(constants.ENGINE_TIMEOUT_SECONDS_KEY, 300))
        max_output_bytes = int(
            input_config.get(constants.ENGINE_MAX_OUTPUT_BYTES_KEY, constants.DEFAULT_MAX_OUTPUT_BYTES)
        )

        cgroup_limit = _get_cgroup_memory_limit()
        if cgroup_limit:
            code = _prepend_memory_limit(code, language, int(cgroup_limit * 0.75))

        command = ["bash", "-c", code] if language == "bash" else [sys.executable, "-c", code]

        result = await _execute_script_common(command, environment, timeout, max_output_bytes)

        if language == "python" and result["stdout"].strip():
            try:
                result["output"] = json.loads(result["stdout"])
            except json.JSONDecodeError:
                lines = [line for line in result["stdout"].strip().split("\n") if line.strip()]
                if lines:
                    with contextlib.suppress(json.JSONDecodeError):
                        result["output"] = json.loads(lines[-1])

        output = ScriptOutput(
            return_code=result["return_code"],
            stdout=result["stdout"],
            stderr=result["stderr"],
            stdout_json=result.get("output"),
        )
        activity_result = _enforce_payload_limit({"output": output.dump(output_config)})

        task_token = base64.b64decode(item.activity_handle)
        handle = temporal_client.get_async_activity_handle(task_token=task_token)  # type: ignore[attr-defined]
        await handle.complete(activity_result)

        logger.info("Work item completed successfully", work_item_id=wi_id)
        return activity_result

    except ScriptExecutionError as e:
        logger.warning("Script execution failed", work_item_id=wi_id, error=str(e))
        task_token = base64.b64decode(item.activity_handle)
        handle = temporal_client.get_async_activity_handle(task_token=task_token)  # type: ignore[attr-defined]
        from temporalio.exceptions import ApplicationError  # noqa: PLC0415
        await handle.fail(ApplicationError(str(e), type="ScriptExecutionError", non_retryable=True))
        raise

    except Exception as e:
        logger.error("Unexpected error processing work item", work_item_id=wi_id, error=str(e))
        task_token = base64.b64decode(item.activity_handle)
        handle = temporal_client.get_async_activity_handle(task_token=task_token)  # type: ignore[attr-defined]
        from temporalio.exceptions import ApplicationError  # noqa: PLC0415
        await handle.fail(ApplicationError(str(e), type=type(e).__name__, non_retryable=True))
        raise


async def _process_item(item: WorkItem, session: AsyncSession, temporal_client: object) -> None:
    """Process one work item: execute, then mark completed or failed."""
    wi_id = str(item.id)
    try:
        await _execute_work_item(item, temporal_client)
        item.status = WorkItemStatus.COMPLETED
        item.completed_at = datetime.now(UTC)
    except Exception:
        item.status = WorkItemStatus.FAILED
        item.completed_at = datetime.now(UTC)
        logger.warning("Work item failed", work_item_id=wi_id)
    finally:
        await session.commit()


async def _poll_loop(session_factory: async_sessionmaker[AsyncSession], temporal_client: object) -> None:
    """Main polling loop: claim and process pending work items every POLL_INTERVAL_SECONDS."""
    logger.info("Execution Plane worker started, polling for work items")
    while True:
        try:
            async with session_factory() as session:
                items = await _claim_pending_items(session)
                if items:
                    logger.info("Claimed work items", count=len(items))
                for item in items:
                    async with session_factory() as item_session:
                        # Re-fetch so changes are tracked in this session
                        refreshed = await item_session.get(WorkItem, item.id)
                        if refreshed:
                            await _process_item(refreshed, item_session, temporal_client)
        except Exception:
            logger.exception("Error in polling loop, will retry")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _create_temporal_client() -> object:
    """Connect to Temporal using the same env vars as the Syntara worker."""
    from pathlib import Path  # noqa: PLC0415

    from temporalio.client import Client  # noqa: PLC0415
    from temporalio.service import TLSConfig  # noqa: PLC0415

    temporal_address = os.environ.get("APP_TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.environ.get("APP_TEMPORAL_NAMESPACE", "default")

    tls: TLSConfig | None = None
    if os.environ.get("APP_S2S_TLS_ENABLED", "").lower() == "true":
        ca = os.environ.get("APP_S2S_TLS_CA_CERT_PATH")
        cert = os.environ.get("APP_S2S_TLS_CERT_PATH")
        key = os.environ.get("APP_S2S_TLS_KEY_PATH")
        if ca and cert and key:
            tls = TLSConfig(
                server_root_ca_cert=Path(ca).read_bytes(),
                client_cert=Path(cert).read_bytes(),
                client_private_key=Path(key).read_bytes(),
            )

    client = await Client.connect(temporal_address, namespace=temporal_namespace, tls=tls)
    logger.info("Connected to Temporal", address=temporal_address, namespace=temporal_namespace, tls_enabled=tls is not None)
    return client


async def _run() -> None:
    database_url = os.environ.get("APP_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL (or APP_DATABASE_URL) environment variable is required")
        sys.exit(1)

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    temporal_client = await _create_temporal_client()
    try:
        await _poll_loop(session_factory, temporal_client)
    finally:
        await engine.dispose()


def main() -> None:
    """Entry point for the execution-plane-worker CLI command."""
    import logging  # noqa: PLC0415

    import structlog  # noqa: PLC0415

    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
