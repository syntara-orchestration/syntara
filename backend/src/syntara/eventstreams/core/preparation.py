"""Preparation results, owned independently of downstream Temporal launchers."""

from copy import deepcopy
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator
from temporalio.api.common.v1 import Payloads
from temporalio.converter import DataConverter

from syntara.eventstreams.adapters.record_identity import record_matches_metadata
from syntara.eventstreams.core.deduplication import (
    DeliveryIdentity,
    DeliveryValue,
    FrozenDeliveryBinding,
    TemporalAcceptance,
    input_fingerprint,
)
from syntara.eventstreams.core.envelope import WorkflowEventEnvelope
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, resolve_trigger_node


class ExecutionCapacityUnavailable(DeliveryValue):
    """The existing soft concurrency gate refused new admission."""

    reason: Literal["execution_capacity"] = "execution_capacity"
    limit: int = Field(gt=0)
    active: int = Field(ge=0)


class PreparationBlocked(DeliveryValue):
    """Runtime references are unavailable; this is not a content rejection."""

    reason: Literal["runtime_unavailable"] = "runtime_unavailable"


class PreparedExecution(DeliveryValue):
    """Detached start arguments, never proof of Temporal acceptance or resolution.

    Arguments remain in memory until acceptance. Retried accepted runs recover
    their original arguments from Temporal.
    """

    identity: DeliveryIdentity
    binding: FrozenDeliveryBinding
    execution_id: UUID
    temporal_workflow_id: str
    workflow_version_id: UUID
    workflow_definition: dict[str, Any] = Field(repr=False)
    trigger_node_id: str
    input_data: dict[str, Any] = Field(repr=False)
    workflow_metadata: dict[str, Any] = Field(repr=False)
    is_builtin: bool

    def execution(self) -> Execution:
        """Build the normal Execution without attaching it to a database session."""
        binding = self.binding
        return Execution(
            id=self.execution_id,
            workflow_id=self.identity.workflow_id,
            workflow_version_id=self.workflow_version_id,
            project_id=UUID(self.workflow_metadata["workflow_context"]["workflow"]["project_id"]),
            temporal_workflow_id=self.temporal_workflow_id,
            status=ExecutionStatus.PENDING,
            trigger_node_id=self.trigger_node_id,
            trigger_type=NodeType.EVENT_SUBSCRIBE_TRIGGER,
            input_data=deepcopy(self.input_data),
            execution_metadata=deepcopy(self.workflow_metadata),
            created_by=binding.execution_principal_id,
            updated_by=binding.execution_principal_id,
            created_at=binding.prepared_at,
            updated_at=binding.prepared_at,
        )

    def workflow_arguments(self) -> list[object]:
        """Match the existing OrchestratorWorkflow's complete argument order."""
        return [
            self.workflow_definition,
            str(self.execution_id),
            self.trigger_node_id,
            self.input_data,
            False,
            None,
            None,
            None,
            self.workflow_metadata,
        ]

    def encoded_arguments_size(self) -> int:
        """Count all serialized argument payloads including their protobuf framing.

        Uses the existing default Temporal converter. This candidate check does
        not include an entire start RPC and is not a transport size guarantee.
        """
        payloads = DataConverter.default.payload_converter.to_payloads(self.workflow_arguments())
        return Payloads(payloads=payloads).ByteSize()


class AcceptedWorkflow(DeliveryValue):
    """Original signed start arguments recovered from an accepted Temporal run."""

    identity: DeliveryIdentity
    temporal_run_id: str = Field(min_length=1, max_length=255)
    arguments: tuple[
        dict[str, Any],
        str,
        str,
        dict[str, Any],
        Literal[False],
        None,
        None,
        None,
        dict[str, Any],
    ] = Field(repr=False)

    @property
    def binding(self) -> FrozenDeliveryBinding:
        """Recover the original version, attribution and input fingerprint."""
        event = self.arguments[8].get("event")
        if not isinstance(event, dict):
            msg = "Accepted workflow has no event metadata"
            raise TypeError(msg)
        return FrozenDeliveryBinding.model_validate(
            {
                **{name: event.get(name) for name in FrozenDeliveryBinding.model_fields if name != "input_fingerprint"},
                "envelope_version": self.arguments[3].get("envelope_version"),
                "input_fingerprint": input_fingerprint(self.arguments[3], self.arguments[8]),
            }
        )

    @model_validator(mode="after")
    def validate_identity(self) -> "AcceptedWorkflow":
        """Require the signed arguments to describe the exact event being recovered."""
        binding = self.binding
        metadata = self.arguments[8]
        event = metadata["event"]
        context = metadata.get("workflow_context")
        if not isinstance(context, dict):
            msg = "Accepted workflow has no workflow context"
            raise TypeError(msg)
        workflow, execution = context.get("workflow"), context.get("execution")
        if not isinstance(workflow, dict) or not isinstance(execution, dict):
            msg = "Accepted workflow has no workflow or execution coordinates"
            raise TypeError(msg)
        envelope = WorkflowEventEnvelope.model_validate(self.arguments[3])
        source = envelope.source_metadata
        _, trigger = resolve_trigger_node(self.arguments[0], self.arguments[2])
        if (
            self.arguments[1] != str(self.identity.execution_id)
            or event.get("identity") != self.identity.model_dump(mode="json")
            or event.get("trigger_node_id") != self.arguments[2]
            or type(event.get("is_builtin")) is not bool
            or workflow.get("id") != str(self.identity.workflow_id)
            or execution.get("id") != str(self.identity.execution_id)
            or execution.get("workflow_version_id") != str(binding.workflow_version_id)
            or source.integration_id != self.identity.integration_identity
            or source.subscription_id != self.identity.subscription_id
            or source.source_generation != self.identity.source_generation
            or not record_matches_metadata(self.identity.record, source)
            or trigger.get("type") != NodeType.EVENT_SUBSCRIBE_TRIGGER
        ):
            msg = "Accepted workflow arguments do not match the expected event identity"
            raise ValueError(msg)
        # Also require a valid original project reference before any DB writes.
        UUID(workflow["project_id"])
        return self

    @property
    def acceptance(self) -> TemporalAcceptance:
        """Return the verified run and original argument fingerprint."""
        return TemporalAcceptance(
            execution_id=self.identity.execution_id,
            temporal_workflow_id=self.identity.temporal_workflow_id,
            temporal_run_id=self.temporal_run_id,
            input_fingerprint=self.binding.input_fingerprint,
        )

    def preparation(self) -> PreparedExecution:
        """Rebuild detached arguments without replacing accepted values."""
        return PreparedExecution(
            identity=self.identity,
            binding=self.binding,
            execution_id=self.identity.execution_id,
            temporal_workflow_id=self.identity.temporal_workflow_id,
            workflow_version_id=self.binding.workflow_version_id,
            workflow_definition=deepcopy(self.arguments[0]),
            trigger_node_id=self.arguments[2],
            input_data=deepcopy(self.arguments[3]),
            workflow_metadata=deepcopy(self.arguments[8]),
            is_builtin=self.arguments[8]["event"]["is_builtin"],
        )
