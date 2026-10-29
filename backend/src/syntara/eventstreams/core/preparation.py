"""Preparation results, owned independently of downstream Temporal launchers."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field
from temporalio.api.common.v1 import Payloads
from temporalio.converter import DataConverter

from syntara.eventstreams.core.deduplication import DeliveryClaim, DeliveryValue


class ExecutionCapacityUnavailable(DeliveryValue):
    """The existing soft concurrency gate refused new admission."""

    reason: Literal["execution_capacity"] = "execution_capacity"
    limit: int = Field(gt=0)
    active: int = Field(ge=0)


class PreparationBlocked(DeliveryValue):
    """Runtime references are unavailable; this is not a content rejection."""

    reason: Literal["runtime_unavailable"] = "runtime_unavailable"


class PreparedExecution(DeliveryValue):
    """Committed preparation, never proof of Temporal acceptance or resolution.

    Returned arguments are detached from persistence. Retries reload persisted
    input and context rather than trusting a caller's mutable argument values.
    """

    claim: DeliveryClaim
    execution_id: UUID
    temporal_workflow_id: str
    workflow_version_id: UUID
    workflow_definition: dict[str, Any] = Field(repr=False)
    trigger_node_id: str
    input_data: dict[str, Any] = Field(repr=False)
    workflow_metadata: dict[str, Any] = Field(repr=False)
    is_builtin: bool

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
