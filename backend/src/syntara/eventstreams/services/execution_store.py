"""Normal Execution persistence after verified Temporal acceptance."""

from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.record_identity import record_matches_source
from syntara.eventstreams.core.deduplication import (
    DeliveryIdentity,
    DeliveryState,
    TemporalAcceptance,
    TerminalDelivery,
    input_fingerprint,
)
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.scheduling_metadata import (
    EVENT_DELIVERY_METADATA_KEY,
    SCHEDULING_STATE_CONFIRMED,
    SCHEDULING_STATE_KEY,
)
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


class EventExecutionStore:
    """Use the caller's short transaction; never perform broker or Temporal I/O."""

    def __init__(self, session: AsyncSession) -> None:
        """Receive a session owned by one lookup or persistence attempt."""
        self.session = session

    @staticmethod
    def _validate(identity: DeliveryIdentity, execution: Execution) -> dict[str, object]:
        metadata = execution.execution_metadata or {}
        event = metadata.get("event")
        if (
            execution.id != identity.execution_id
            or execution.workflow_id != identity.workflow_id
            or execution.temporal_workflow_id != identity.temporal_workflow_id
            or execution.trigger_type != NodeType.EVENT_SUBSCRIBE_TRIGGER
            or not isinstance(event, dict)
            or event.get("identity") != identity.model_dump(mode="json")
            or event.get("workflow_version_id") != str(execution.workflow_version_id)
            or event.get("trigger_node_id") != execution.trigger_node_id
            or event.get("execution_principal_id") != str(execution.created_by)
        ):
            msg = "Retained Execution does not match the expected event identity"
            raise ValueError(msg)
        evidence = metadata.get(EVENT_DELIVERY_METADATA_KEY)
        if not isinstance(evidence, dict):
            msg = "Retained Execution has no confirmed scheduling evidence"
            raise TypeError(msg)
        return evidence

    @classmethod
    def _terminal(cls, identity: DeliveryIdentity, execution: Execution) -> TerminalDelivery:
        evidence = cls._validate(identity, execution)
        if (
            evidence.get(SCHEDULING_STATE_KEY) != SCHEDULING_STATE_CONFIRMED
            or evidence.get("identity_digest") != identity.digest
            or evidence.get("temporal_workflow_id") != identity.temporal_workflow_id
            or evidence.get("input_fingerprint")
            != input_fingerprint(
                execution.input_data,
                {
                    key: value
                    for key, value in (execution.execution_metadata or {}).items()
                    if key != EVENT_DELIVERY_METADATA_KEY
                },
            )
        ):
            msg = "Retained Execution has no matching confirmed acceptance"
            raise ValueError(msg)
        return TerminalDelivery.model_validate(
            {
                "identity": identity,
                "state": DeliveryState.SCHEDULED,
                "execution_id": execution.id,
                "temporal_run_id": evidence.get("temporal_run_id"),
                "execution_confirmed_at": evidence.get("confirmed_at"),
                "resolved_at": evidence.get("resolved_at", evidence.get("confirmed_at")),
            }
        )

    async def lookup(self, identity: DeliveryIdentity) -> TerminalDelivery | None:
        """Read normal Execution evidence before looking up Temporal or decoding."""
        execution = await self.session.get(Execution, identity.execution_id, populate_existing=True)
        return None if execution is None else self._terminal(identity, execution)

    async def persist(self, prepared: PreparedExecution, acceptance: TemporalAcceptance) -> TerminalDelivery:
        """Save the accepted run once without changing an existing Execution status."""
        identity, binding = prepared.identity, prepared.binding
        if (
            acceptance.execution_id != identity.execution_id
            or acceptance.temporal_workflow_id != identity.temporal_workflow_id
            or acceptance.input_fingerprint != binding.input_fingerprint
        ):
            msg = "Acceptance does not match the original workflow arguments"
            raise ValueError(msg)
        lifecycle = await lock_source_lifecycle(self.session, identity.source_id)
        if lifecycle is None or (
            lifecycle[0].workflow_id != identity.workflow_id
            or lifecycle[0].id != identity.subscription_id
            or lifecycle[1].generation != identity.source_generation
            or lifecycle[1].deployment_id != identity.deployment_id
            or lifecycle[1].integration_identity != identity.integration_identity
            or not record_matches_source(identity.record, lifecycle[1].configuration)
        ):
            msg = "Accepted workflow source is unavailable"
            raise ValueError(msg)
        execution = await self.session.get(
            Execution, identity.execution_id, with_for_update=True, populate_existing=True
        )
        if execution is None:
            execution = prepared.execution()
            self.session.add(execution)
        else:
            original = prepared.execution()
            if (
                execution.workflow_version_id != original.workflow_version_id
                or execution.project_id != original.project_id
                or execution.created_by != original.created_by
                or execution.input_data != original.input_data
                or {
                    key: value
                    for key, value in (execution.execution_metadata or {}).items()
                    if key != EVENT_DELIVERY_METADATA_KEY
                }
                != prepared.workflow_metadata
            ):
                msg = "Retained Execution conflicts with accepted workflow arguments"
                raise ValueError(msg)
            evidence = (execution.execution_metadata or {}).get(EVENT_DELIVERY_METADATA_KEY, {})
            if not isinstance(evidence, dict):
                msg = "Retained Execution has invalid scheduling metadata"
                raise TypeError(msg)
            if evidence.get(SCHEDULING_STATE_KEY) == SCHEDULING_STATE_CONFIRMED:
                terminal = self._terminal(identity, execution)
                if terminal.temporal_run_id != acceptance.temporal_run_id:
                    msg = "Accepted run conflicts with retained confirmation"
                    raise ValueError(msg)
                return terminal
        now = datetime.now(UTC).isoformat()
        execution.execution_metadata = {
            **prepared.workflow_metadata,
            EVENT_DELIVERY_METADATA_KEY: {
                "identity_digest": identity.digest,
                SCHEDULING_STATE_KEY: SCHEDULING_STATE_CONFIRMED,
                "input_fingerprint": binding.input_fingerprint,
                "temporal_workflow_id": identity.temporal_workflow_id,
                "temporal_run_id": acceptance.temporal_run_id,
                "confirmed_at": now,
                "resolved_at": now,
            },
        }
        await self.session.flush()
        return self._terminal(identity, execution)
