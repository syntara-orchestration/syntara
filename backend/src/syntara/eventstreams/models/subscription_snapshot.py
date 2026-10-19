"""Immutable SubscriptionSnapshot: frozen processing context for one attempt.

A ``SubscriptionSnapshot`` is the immutable projection of an
``EventSubscription`` and its active ``EventSubscriptionSource`` that downstream
admission and recovery consume. It freezes the published version, source
generation, configuration revision, typed source configuration and principal
references so a prepared binding survives later publication changes. Paused,
unpublished and retired subscriptions can still produce a snapshot so downstream
recovery remains able to discover them without new consumers.

This module performs no database or broker I/O; the service assembles snapshots
from already-loaded rows.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, field_serializer, field_validator
from sqlmodel import SQLModel

from syntara.eventstreams.adapters.source_configuration import SourceConfiguration
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription


def _deep_freeze(value: Any) -> Any:  # noqa: ANN401
    """Detach and recursively freeze a JSON value (dicts -> read-only, lists -> tuples)."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _to_plain_json(value: Any) -> Any:  # noqa: ANN401
    """Convert a frozen JSON value back to plain dict/list for serialization."""
    if isinstance(value, Mapping):
        return {key: _to_plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_json(item) for item in value]
    return value


class SubscriptionSnapshot(SQLModel):
    """Frozen, transport-neutral view of a subscription and its active source."""

    subscription_id: UUID
    workflow_id: UUID
    project_id: UUID
    trigger_node_id: str
    published_version_id: UUID
    configuration_revision: int

    source_id: UUID
    source_generation: int
    deployment_id: UUID
    transport: str
    integration_id: UUID | None
    integration_identity: UUID
    configuration: SourceConfiguration

    runtime_credential_id: UUID | None
    # Stored as a recursively read-only mapping so the frozen processing context
    # cannot be mutated (directly or nested) or aliased to the live subscription.
    input_schema: Mapping[str, Any] | None

    desired_enabled: bool
    paused: bool
    retired: bool
    enabled_by: UUID | None

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True
    )

    @field_validator("input_schema", mode="after")
    @classmethod
    def _freeze_input_schema(cls, value: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
        """Detach and recursively freeze the published input schema."""
        return None if value is None else _deep_freeze(value)

    @field_serializer("input_schema")
    def _serialize_input_schema(self, value: Mapping[str, Any] | None, _info: Any) -> Any:  # noqa: ANN401
        """Serialize the frozen schema back to plain JSON (dicts/lists)."""
        return None if value is None else _to_plain_json(value)

    @classmethod
    def from_models(
        cls,
        subscription: EventSubscription,
        source: EventSubscriptionSource,
    ) -> "SubscriptionSnapshot":
        """Build an immutable snapshot from an already-loaded subscription and source."""
        return cls(
            subscription_id=subscription.id,
            workflow_id=subscription.workflow_id,
            project_id=subscription.project_id,
            trigger_node_id=subscription.trigger_node_id,
            published_version_id=subscription.published_version_id,
            configuration_revision=subscription.configuration_revision,
            source_id=source.id,
            source_generation=source.generation,
            deployment_id=source.deployment_id,
            transport=source.transport,
            integration_id=source.integration_id,
            integration_identity=source.integration_identity,
            configuration=source.configuration,
            runtime_credential_id=subscription.runtime_credential_id,
            input_schema=subscription.input_schema,
            desired_enabled=subscription.desired_enabled,
            paused=subscription.paused,
            retired=subscription.retired,
            enabled_by=subscription.enabled_by,
        )
