"""Database aggregation queries for periodic analytics.

All queries are read-only, non-locking, stateless snapshots
of the current database state. No time-based filtering.
Soft-deleted records are excluded where applicable (workflows, executions).
"""

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.orm import InstrumentedAttribute
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.identity_providers.models.identity_provider import IdentityProvider
from syntara.integrations.models.integration import Integration
from syntara.telemetry.events.integration_health import (
    CredentialHealth,
    CredentialInfo,
    IdentityProviderHealth,
    IdentityProviderInfo,
    IntegrationHealth,
    IntegrationInfo,
)
from syntara.telemetry.events.system_analytics import (
    CredentialCounts,
    ExecutionCounts,
    ModelUsage,
    ToolCounts,
    WorkflowCounts,
)
from syntara.tool_manager.models.usage_counter import CounterType, UsageCounter
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow


async def query_workflow_counts(session: AsyncSession) -> WorkflowCounts:
    """Query current workflow counts from database (excludes soft-deleted)."""
    not_deleted = Workflow.deleted_at.is_(None)  # type: ignore[union-attr]
    total = await session.scalar(select(func.count(Workflow.id)).where(not_deleted))  # type: ignore[arg-type]
    is_enabled = Workflow.is_enabled.is_(True)  # type: ignore[attr-defined]
    enabled = await session.scalar(
        select(func.count(Workflow.id)).where(  # type: ignore[arg-type]
            is_enabled,
            not_deleted,
        )
    )
    return WorkflowCounts(
        total=total or 0,
        enabled=enabled or 0,
        disabled=(total or 0) - (enabled or 0),
    )


async def query_execution_counts(session: AsyncSession) -> ExecutionCounts:
    """Query current execution counts from database (excludes soft-deleted)."""
    not_deleted = Execution.deleted_at.is_(None)  # type: ignore[union-attr]
    result = await session.exec(
        select(Execution.status, func.count(Execution.id)).where(not_deleted).group_by(Execution.status)  # type: ignore[call-overload,arg-type]
    )
    status_counts: dict[str, int] = {}
    for row in result:
        key = row[0].value if isinstance(row[0], ExecutionStatus) else str(row[0])
        status_counts[key] = row[1]

    avg_duration = await session.scalar(
        select(func.avg(func.extract("epoch", Execution.completed_at - Execution.created_at))).where(  # type: ignore[operator,arg-type]
            Execution.completed_at.isnot(None),  # type: ignore[union-attr]
            not_deleted,
        )
    )

    by_trigger_type = await _query_execution_counts_by_column(session, Execution.trigger_type, not_deleted)  # type: ignore[arg-type]
    by_interface = await _query_execution_counts_by_column(session, Execution.interface, not_deleted)  # type: ignore[arg-type]

    return ExecutionCounts(
        total=sum(status_counts.values()),
        completed=status_counts.get("completed", 0),
        failed=status_counts.get("failed", 0),
        cancelled=status_counts.get("cancelled", 0),
        running=status_counts.get("running", 0),
        pending=status_counts.get("pending", 0),
        paused=status_counts.get("paused", 0),
        avg_duration_seconds=float(avg_duration) if avg_duration is not None else 0.0,
        by_trigger_type=by_trigger_type,
        by_interface=by_interface,
    )


async def _query_execution_counts_by_column(
    session: AsyncSession,
    column: InstrumentedAttribute[str | None],
    not_deleted: ColumnElement[bool],
) -> dict[str, int]:
    """Group execution counts by a nullable string column, excluding NULLs."""
    result = await session.exec(
        select(column, func.count(Execution.id))  # type: ignore[call-overload,arg-type]
        .where(not_deleted, column.isnot(None))
        .group_by(column)
    )
    return {str(key): int(count) for key, count in result}


async def query_credential_counts(session: AsyncSession) -> CredentialCounts:
    """Query current credential counts from database.

    Returns total count, per-type breakdown by credential type name,
    and count of distinct credentials actively referenced in workflow nodes.
    """
    result = await session.exec(
        select(  # type: ignore[call-overload]
            CredentialType.name,
            func.count(Credential.id),  # type: ignore[arg-type]
        )
        .join(CredentialType, Credential.credential_type_id == CredentialType.id)
        .group_by(CredentialType.name)
    )
    counts_by_type: dict[str, int] = {}
    for type_name, count in result:
        counts_by_type[type_name] = int(count)

    used_in_nodes = await _query_credentials_used_in_nodes(session)

    return CredentialCounts(
        total=sum(counts_by_type.values()),
        type=counts_by_type,
        used_in_nodes=used_in_nodes,
    )


async def _query_credentials_used_in_nodes(session: AsyncSession) -> int:
    """Count distinct credential IDs referenced in active workflow version nodes.

    Joins workflow_versions with workflows to find the current active version
    for each non-deleted workflow, then extracts credential_id from each node's
    parameters using jsonb_path_query.
    """
    # jsonb_path_query extracts all credential_id values from nodes[*].parameters
    # in a single path expression, replacing CROSS JOIN LATERAL + arrow operators.
    stmt = text("""
        SELECT COUNT(DISTINCT cred_id)
        FROM workflow_versions wv
        JOIN workflows w
            ON w.id = wv.workflow_id
            AND w.current_version = wv.version
            AND w.deleted_at IS NULL
        CROSS JOIN LATERAL jsonb_path_query(
            wv.workflow_definition, '$.nodes[*].parameters.credential_id'
        ) AS cred_id
        WHERE wv.deleted_at IS NULL
    """)
    result = await session.scalar(stmt)
    return int(result) if result else 0


async def query_model_usage(session: AsyncSession) -> list[ModelUsage]:
    """Query aggregated token usage per model from database.

    Joins token_usage_records with invocations to get the model name,
    then aggregates prompt_tokens, completion_tokens, and invocation count
    grouped by model. Only includes records with a known model and actual
    (post-LLM) token counts.
    """
    stmt = (
        select(  # type: ignore[call-overload]
            Invocation.model_name,
            func.coalesce(func.sum(TokenUsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(TokenUsageRecord.completion_tokens), 0),
            func.coalesce(func.count(TokenUsageRecord.id), 0),  # type: ignore[arg-type]
        )
        .join(Invocation, TokenUsageRecord.invocation_id == Invocation.id)
        .where(
            Invocation.model_name.isnot(None),  # type: ignore[union-attr]
            TokenUsageRecord.prompt_tokens.isnot(None),  # type: ignore[union-attr]
        )
        .group_by(Invocation.model_name)
    )
    result = await session.exec(stmt)
    return [
        ModelUsage(
            model=model_name,
            total_prompt_tokens=int(prompt),
            total_completion_tokens=int(completion),
            total_tokens=int(prompt) + int(completion),
            invocation_count=int(count),
        )
        for model_name, prompt, completion, count in result
    ]


async def query_tool_counts(session: AsyncSession) -> ToolCounts:
    """Query all-time cumulative tool execution counts from usage_counters table."""
    tool_filter = UsageCounter.counter_type == CounterType.TOOL
    result = await session.exec(
        select(  # type: ignore[call-overload]
            func.coalesce(func.sum(UsageCounter.request_count), 0),
            func.coalesce(func.sum(UsageCounter.success_count), 0),
            func.coalesce(func.sum(UsageCounter.error_count), 0),
            func.coalesce(func.sum(UsageCounter.timeout_count), 0),
            func.count(UsageCounter.tool_id.distinct()),  # type: ignore[union-attr]
        ).where(tool_filter)  # type: ignore[arg-type]
    )
    row = result.one()
    return ToolCounts(
        success_count=int(row[1]),
        error_count=int(row[2]),
        timeout_count=int(row[3]),
        distinct_tools=int(row[4]),
    )


def get_enabled_feature_flags() -> list[str]:
    """Return list of enabled feature flag names.

    Currently returns an empty list — no feature flag system exists.
    """
    return []


async def query_integration_health(session: AsyncSession) -> IntegrationHealth:
    """Query health status of configured integrations grouped by type and status."""
    integration_result = await session.exec(
        select(  # type: ignore[call-overload]
            Integration.integration_type,
            Integration.enabled,
            func.count(Integration.id),  # type: ignore[arg-type]
        ).group_by(Integration.integration_type, Integration.enabled)
    )

    items: dict[str, IntegrationInfo] = {}
    total = 0
    for integration_type, is_enabled, count in integration_result:
        type_key = str(integration_type)
        info = items.setdefault(type_key, IntegrationInfo())
        if is_enabled:
            info.enabled = count
        else:
            info.disabled = count
        total += count

    return IntegrationHealth(
        items=items,
        total=total,
    )


async def query_identity_provider_health(session: AsyncSession) -> IdentityProviderHealth:
    """Query health status of configured identity providers grouped by type and status."""
    provider_type_col = IdentityProvider.configuration["provider_type"].astext.label("provider_type")  # type: ignore[index]

    provider_result = await session.exec(
        select(  # type: ignore[call-overload]
            provider_type_col,
            IdentityProvider.enabled,
            func.count(IdentityProvider.id),  # type: ignore[arg-type]
        ).group_by(provider_type_col, IdentityProvider.enabled)
    )

    items: dict[str, IdentityProviderInfo] = {}
    total = 0
    for provider_type, is_enabled, count in provider_result:
        info = items.setdefault(provider_type, IdentityProviderInfo())
        if is_enabled:
            info.enabled = count
        else:
            info.disabled = count
        total += count

    return IdentityProviderHealth(
        items=items,
        total=total,
    )


async def query_credential_health(session: AsyncSession) -> CredentialHealth:
    """Query health status of configured credentials grouped by type and status."""
    credential_result = await session.exec(
        select(  # type: ignore[call-overload]
            CredentialType.name,
            Credential.enabled,
            func.count(Credential.id),  # type: ignore[arg-type]
        )
        .join(CredentialType, Credential.credential_type_id == CredentialType.id)
        .group_by(CredentialType.name, Credential.enabled)
    )

    items: dict[str, CredentialInfo] = {}
    total_enabled = 0
    total_disabled = 0
    for type_name, is_enabled, count in credential_result:
        info = items.setdefault(type_name, CredentialInfo())
        if is_enabled:
            info.enabled = count
            total_enabled += count
        else:
            info.disabled = count
            total_disabled += count

    return CredentialHealth(
        items=items,
        total=total_enabled + total_disabled,
        enabled=total_enabled,
        disabled=total_disabled,
    )
