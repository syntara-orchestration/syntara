"""Translate AO target CRUD into EP commands without storing target state in AO."""

from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from execution_plane_client.commands.base import CommandPayload
from execution_plane_client.commands.targets import KubernetesPlacement as CommandKubernetesPlacement
from execution_plane_client.commands.targets import TargetDelete, TargetRegister, TargetUpdate
from fastapi import HTTPException, status
from pydantic import model_validator
from pydantic.json_schema import SkipJsonSchema
from sqlmodel import Field, SQLModel

from syntara.execution_plane.client import (
    EP_AUDIENCE,
    EP_CLIENT_ID,
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
)


class KubernetesTargetPlacement(CommandKubernetesPlacement):
    """Validated Kubernetes placement for writes, using EP's shared command contract."""


class ExecutionTargetCreate(SQLModel):
    """A Kubernetes target on the single cluster provisioned at installation."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=255)
    placement: KubernetesTargetPlacement
    labels: dict[str, str] = Field(default_factory=dict)
    is_default: bool = False


class ExecutionTargetUpdate(SQLModel):
    """Patch mutable target fields. Placement requires a namespace; omitted selectors are retained."""

    model_config = {"extra": "forbid", "json_schema_extra": {"minProperties": 1}}

    name: Annotated[str, Field(min_length=1, max_length=255)] | SkipJsonSchema[None] = None
    placement: KubernetesTargetPlacement | SkipJsonSchema[None] = None
    labels: dict[str, str] | SkipJsonSchema[None] = None
    is_default: bool | SkipJsonSchema[None] = None
    enabled: bool | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        """Reject empty patches and clearing required values before sending a command."""
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            message = "Supply at least one target field; target fields cannot be null"
            raise ValueError(message)
        return self


class ExecutionTargetDeleteAccepted(SQLModel):
    """EP accepted deletion; draining and physical removal happen independently."""

    id: UUID
    accepted: Literal[True] = True


class _InstalledCluster(SQLModel):
    """Installed cluster fields used to create targets."""

    id: UUID
    endpoint: str


async def _installed_cluster(client: ExecutionPlaneHttpClient) -> _InstalledCluster:
    """Resolve the single installed cluster from EP inventory."""
    page = await client.list_clusters(limit=2)
    if len(page["resources"]) != 1 or page.get("next") or page.get("prev"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Expected exactly one installed Execution Plane cluster")
    resource = page["resources"][0]
    if resource.get("id") is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Installed Execution Plane cluster has no ID")
    return _InstalledCluster.model_validate(resource)


async def _submit_target_command(client: ExecutionPlaneHttpClient, command: CommandPayload, target_id: UUID) -> None:
    """Require EP to confirm that the command affected the intended target."""
    receipt = await client.submit_command(
        command.to_message(source_id=EP_CLIENT_ID, destination_id=EP_AUDIENCE, client_id=EP_CLIENT_ID)
    )
    if (
        receipt.resource is None
        or receipt.resource.kind != "execution_target"
        or receipt.resource.resource_id != target_id
    ):
        message = "Execution Plane returned an invalid target receipt"
        raise ExecutionPlaneRejectedError(message)


async def _read_target(client: ExecutionPlaneHttpClient, target_id: UUID) -> dict[str, object]:
    """Read back the authoritative resource after a create or update command."""
    resource = await client.get_execution_target(target_id=target_id)
    if resource.get("id") != str(target_id):
        message = "Execution Plane returned a different target"
        raise ExecutionPlaneRejectedError(message)
    return resource


async def create_target(client: ExecutionPlaneHttpClient, data: ExecutionTargetCreate) -> dict[str, object]:
    """Create on the installed physical cluster; authentication remains on it."""
    cluster = await _installed_cluster(client)
    target_id = uuid4()
    command = TargetRegister(
        resource_id=target_id,
        cluster_id=cluster.id,
        name=data.name,
        backend_type="vanilla_k8s",
        endpoint=cluster.endpoint,
        credential_ref=UUID(int=0),  # Kubernetes execution uses the cluster's credential reference.
        placement=data.placement,
        labels=data.labels,
        is_default=data.is_default,
    )
    await _submit_target_command(client, command, target_id)
    return await _read_target(client, target_id)


async def update_target(
    client: ExecutionPlaneHttpClient, target_id: UUID, data: ExecutionTargetUpdate
) -> dict[str, object]:
    """Keep omission distinct from clearing labels and scheduling lists."""
    fields = data.model_dump(exclude_unset=True)
    if data.placement is not None:
        fields["placement"] = data.placement
    command = TargetUpdate(resource_id=target_id, **fields)
    await _submit_target_command(client, command, target_id)
    return await _read_target(client, target_id)


async def delete_target(client: ExecutionPlaneHttpClient, target_id: UUID) -> None:
    """Request EP's drain lifecycle; deletion is not immediate."""
    await _submit_target_command(client, TargetDelete(resource_id=target_id), target_id)
