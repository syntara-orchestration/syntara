"""Node execution telemetry event model and builder.

Defines the SQLModel model for node execution events and a builder
class for constructing events from node execution context.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import field_validator
from sqlmodel import Field

if TYPE_CHECKING:
    from uuid import UUID

from syntara.telemetry.events.base import BaseTelemetryEvent
from syntara.workflows.workflow_engine.models.workflow_definition import (  # noqa: TC001
    ActivityTerminalStatus,
    NodeType,
)

_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)


class NodeExecutionEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a node executes within a workflow.

    Attributes:
        workflow_execution_id: Links to parent workflow execution (UUID v4).
        node_type: Type of node executed.
        node_hash: SHA-256 hash of node definition.
        status: Node execution outcome.
        inbound_nodes: Optional array of node hashes that led to this node.
        outbound_nodes: Optional array of node hashes triggered by this node.
        error_type: Categorized error type if node failed, null otherwise.

    """

    workflow_execution_id: str = Field(description="Unique workflow execution identifier (UUID v4)")
    node_type: NodeType
    node_hash: str = Field(description="SHA-256 hash of node definition")
    status: ActivityTerminalStatus
    duration_ms: int | None = Field(
        default=None,
        description="Node execution duration in milliseconds",
    )

    @field_validator("node_hash")
    @classmethod
    def _validate_hash(cls, v: str) -> str:
        if not _SHA256_PATTERN.match(v):
            msg = "node_hash must be a 64-character hex string"
            raise ValueError(msg)
        return v

    inbound_nodes: list[str] | None = Field(
        default=None,
        description="Optional array of node hashes that led to this node's execution",
    )
    outbound_nodes: list[str] | None = Field(
        default=None,
        description="Optional array of node hashes triggered by this node",
    )
    error_type: str | None = Field(
        default=None,
        description="Name of the exception that caused the error, null otherwise",
    )


class NodeExecutionEventBuilder:
    """Builder for constructing node execution telemetry events."""

    @staticmethod
    @lru_cache(maxsize=256)
    def _calculate_definition_hash(canonical_json: str) -> str:
        """Calculate SHA-256 hash of a node definition for anonymized identification.

        Args:
            canonical_json: Canonical JSON string representation of the node definition.

        Returns:
            64-character hex string SHA-256 hash.

        """
        return hashlib.sha256(canonical_json.encode()).hexdigest()

    def build_event(
        self,
        execution_id: str,
        node_type: NodeType,
        node_def: dict[str, object],
        status: ActivityTerminalStatus,
        entitlement_id: str,
        duration_ms: int | None = None,
        inbound_nodes: list[str] | None = None,
        outbound_nodes: list[str] | None = None,
        error_type: str | None = None,
        request_id: UUID | None = None,
    ) -> NodeExecutionEvent:
        """Build a node execution event.

        Args:
            execution_id: Links to parent workflow execution (UUID v4).
            node_type: Type of node executed.
            node_def: Node definition dictionary for hash calculation.
            status: Node execution outcome.
            entitlement_id: Installation entitlement identifier.
            duration_ms: Node execution duration in milliseconds.
            inbound_nodes: Optional array of preceding node hashes.
            outbound_nodes: Optional array of following node hashes.
            error_type: Name of the exception that caused the error.
            request_id: Optional X-Request-Id from the originating HTTP request.

        Returns:
            NodeExecutionEvent instance.

        """
        canonical_json = json.dumps(node_def, sort_keys=True)
        node_hash = self._calculate_definition_hash(canonical_json)
        return NodeExecutionEvent(
            workflow_execution_id=execution_id,
            node_type=node_type,
            node_hash=node_hash,
            status=status,
            duration_ms=duration_ms,
            inbound_nodes=inbound_nodes,
            outbound_nodes=outbound_nodes,
            error_type=error_type,
            entitlement_id=entitlement_id,
            request_id=request_id,
        )
