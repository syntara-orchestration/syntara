"""Standalone execution-cluster registration through EP's cluster command API.

Mirrors targets.py: AO translates a management-API call into EP commands without
storing cluster state in AO. Unlike the Integration sync path
(cluster_sync_commands.apply_integration_cluster), registration here is not
driven by an Integration row: the caller names the cluster, its endpoint, and an
existing AO credential that can manage it. This is what lets aap-dev register
the Kind cluster (and any admin register a standalone cluster) through AO
instead of posting ClusterProvision straight to the EP API (see the
cluster-registration story tracked on the AO board).
"""

from uuid import NAMESPACE_URL, UUID, uuid5

from execution_plane_client.commands.clusters import ClusterProvision
from pydantic import BaseModel, Field

from syntara.execution_plane.client import (
    EP_AUDIENCE,
    EP_CLIENT_ID,
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
)

# EP treats a provision at an unchanged desired revision as idempotent, so a
# fixed revision keeps retries safe without AO-side revision bookkeeping.
_STANDALONE_CLUSTER_REVISION = 1


class ClusterRegistrationCreate(BaseModel):
    """A standalone cluster registration: the cluster plus its default target."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=255)
    endpoint: str = Field(max_length=2048)
    namespace: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
        description="Namespace the dispatcher ServiceAccount and Jobs run in",
    )
    credential_ref: UUID = Field(description="Existing AO credential that can manage the cluster")
    ca_certificate: str | None = Field(default=None, max_length=65536, repr=False)
    labels: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


def standalone_cluster_resource_key(name: str) -> UUID:
    """Derive a stable resource key so repeated registrations update in place.

    ClusterProvision keys registrations by source_integration_id; a deterministic
    UUID5 over the cluster name keeps POST idempotent per name without AO-side
    state.
    """
    return uuid5(NAMESPACE_URL, f"https://execution-plane.ao/clusters/{name}")


async def register_cluster(
    client: ExecutionPlaneHttpClient,
    *,
    resource_key: UUID,
    name: str,
    endpoint: str,
    namespace: str,
    credential_ref: UUID,
    ca_certificate: str | None = None,
    labels: dict[str, str] | None = None,
    enabled: bool = True,
) -> dict[str, object]:
    """Register (or idempotently re-apply) a standalone cluster and its default target.

    Uses EP's synchronous cluster.provision command, like the Konflux e2e did
    by hand: the handler creates or updates the Cluster and the default
    ExecutionTarget in one step. Provisioning at a fixed desired revision is
    idempotent, so retries and re-registrations with the same desired state are
    safe; a changed desired state at the same revision is rejected by EP.
    """
    command = ClusterProvision(
        resource_key=resource_key,
        desired_revision=_STANDALONE_CLUSTER_REVISION,
        name=name,
        endpoint=endpoint,
        namespace=namespace,
        credential_ref=credential_ref,
        ca_certificate=ca_certificate,
        labels=labels or {},
        enabled=enabled,
    )
    receipt = await client.submit_command(
        command.to_message(source_id=EP_CLIENT_ID, destination_id=EP_AUDIENCE, client_id=EP_CLIENT_ID)
    )
    if receipt.resource is None or receipt.resource.kind != "cluster":
        message = "Execution Plane returned an invalid cluster receipt"
        raise ExecutionPlaneRejectedError(message)
    return await _read_cluster(client, resource_key)


async def _read_cluster(client: ExecutionPlaneHttpClient, resource_key: UUID) -> dict[str, object]:
    """Read back the authoritative cluster by its stable source key."""
    page = await client.list_clusters(limit=2, filters={"source_integration_id": str(resource_key)})
    resources: list[dict[str, object]] = page["resources"]
    if len(resources) != 1 or page.get("next") or page.get("prev"):
        message = "Expected exactly one Execution Plane cluster for the registration"
        raise ExecutionPlaneRejectedError(message)
    return resources[0]
