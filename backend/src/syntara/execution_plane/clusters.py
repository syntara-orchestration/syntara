"""Standalone execution-cluster registration through EP's cluster command API.

Mirrors targets.py: AO translates a management-API call into EP commands without
storing cluster state in AO. Unlike the Integration sync path
(cluster_sync_commands.apply_integration_cluster), registration here is not
driven by an Integration row: the caller names the cluster, its endpoint, and an
existing AO credential that can manage it. This is what lets aap-dev register
the Kind cluster (and any admin register a standalone cluster) through AO
instead of posting ClusterRegister straight to the EP API (see the
cluster-registration story tracked on the AO board).

Clusters carry no namespace: the dispatch namespace is chosen by the execution
targets created on the cluster through their own dedicated endpoint.
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from execution_plane_client.commands.clusters import ClusterRegister
from pydantic import BaseModel, Field

from syntara.execution_plane.client import (
    EP_AUDIENCE,
    EP_CLIENT_ID,
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
)


class ClusterRegistrationCreate(BaseModel):
    """A standalone cluster registration; dispatch namespaces come from targets."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=255)
    endpoint: str = Field(max_length=2048)
    credential_ref: UUID = Field(description="Existing AO credential that can manage the cluster")
    ca_certificate: str | None = Field(default=None, max_length=65536, repr=False)
    labels: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


def standalone_cluster_resource_id(name: str) -> UUID:
    """Derive a stable cluster id so repeated registrations update in place.

    EP clusters are addressed by a caller-supplied physical id (shared with the
    owning AO Integration on that path); a deterministic UUID5 over the cluster
    name keeps POST idempotent per name without AO-side state.
    """
    return uuid5(NAMESPACE_URL, f"https://execution-plane.ao/clusters/{name}")


async def register_cluster(
    client: ExecutionPlaneHttpClient,
    *,
    resource_id: UUID,
    name: str,
    endpoint: str,
    credential_ref: UUID,
    ca_certificate: str | None = None,
    labels: dict[str, str] | None = None,
    enabled: bool = True,
) -> dict[str, object]:
    """Register (or idempotently re-apply) a standalone cluster.

    Sends EP's cluster.register command with the caller-supplied physical id;
    the handler creates or replaces the cluster's desired configuration at that
    id, so re-posting the same desired state is safe. The dispatch namespace is
    not part of the cluster: create execution targets on the cluster for that.
    """
    command = ClusterRegister(
        resource_id=resource_id,
        name=name,
        endpoint=endpoint,
        credential_ref=credential_ref,
        ca_certificate=ca_certificate,
        labels=labels or {},
        enabled=enabled,
    )
    receipt = await client.submit_command(
        command.to_message(source_id=EP_CLIENT_ID, destination_id=EP_AUDIENCE, client_id=EP_CLIENT_ID)
    )
    if receipt.resource is None or receipt.resource.kind != "cluster" or receipt.resource.resource_id != resource_id:
        message = "Execution Plane returned an invalid cluster receipt"
        raise ExecutionPlaneRejectedError(message)
    return await _read_cluster(client, resource_id)


async def _read_cluster(client: ExecutionPlaneHttpClient, resource_id: UUID) -> dict[str, object]:
    """Read back the authoritative cluster by its physical id."""
    page = await client.list_clusters(limit=2, filters={"id": str(resource_id)})
    resources: list[dict[str, object]] = page["resources"]
    if len(resources) != 1 or page.get("next") or page.get("prev"):
        message = "Expected exactly one Execution Plane cluster for the registration"
        raise ExecutionPlaneRejectedError(message)
    return resources[0]
