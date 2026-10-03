"""Register a real Kubernetes ExecutionTarget for Execution Plane integration tests.

The EP-dispatch integration tests run a workflow whose ``script`` node is executed
as a cold-start pod in a real Kubernetes cluster. The cluster itself is provisioned
*outside* the test suite — a local ``kind`` cluster during development,
``helm/kind-action`` in CI — and its coordinates are passed in through environment
variables:

* ``EP_IT_K8S_ENDPOINT`` — API server URL (e.g. ``https://127.0.0.1:34567``)
* ``EP_IT_K8S_TOKEN``    — ServiceAccount **bearer token** (the vanilla-k8s
  transport requires a token; a kubeconfig/client-cert will not work)
* ``EP_IT_K8S_NAMESPACE`` — target namespace (default ``execution-plane``)

The integration CI job always stands up a kind cluster and sets these, so the
suite runs against a real cluster. When they are absent (e.g. a local run without
a cluster), :func:`ep_cluster_configured` reports ``False`` and the ``temporal_env``
fixture skips target registration, leaving non-EP integration tests runnable while
the script-dispatch tests fail for lack of a cluster.

The actual Cluster/ExecutionTarget provisioning is delegated to the EP dev tooling
(``dev_cli._register_environment_record``) so the test path and the developer
``ep-dev-up`` path stay in sync; only the cluster source differs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# dev_cli lives beside the EP worker tools, which are not importable as a package
# from the backend test tree. Add the directory to sys.path so we can reuse its
# registration helpers rather than duplicating the provisioning logic.
_TOOLS_DIR = Path(__file__).resolve().parents[2] / "execution-plane" / "tools"

ENDPOINT_ENV = "EP_IT_K8S_ENDPOINT"
TOKEN_ENV = "EP_IT_K8S_TOKEN"  # noqa: S105 — env var *name*, not a secret value
NAMESPACE_ENV = "EP_IT_K8S_NAMESPACE"
DEFAULT_NAMESPACE = "execution-plane"
CLUSTER_NAME = "integration-test"


def ep_cluster_configured() -> bool:
    """Return whether a real Kubernetes cluster is configured for EP dispatch."""
    return bool(os.environ.get(ENDPOINT_ENV) and os.environ.get(TOKEN_ENV))


async def register_ep_cluster_target(database_url: str) -> None:
    """Provision a healthy default ExecutionTarget from the configured cluster env.

    Reuses ``dev_cli._register_environment_record`` so the resulting Cluster +
    default ExecutionTarget are identical to a developer ``ep-dev-up`` registration,
    which ``bootstrap_local_cluster`` then recognises as healthy and leaves alone.
    """
    if str(_TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(_TOOLS_DIR))
    from dev_cli import (
        EnvironmentDetails,
        EnvironmentProvider,
        _register_environment_record,
    )

    details = EnvironmentDetails(
        provider=EnvironmentProvider.KIND,
        name=CLUSTER_NAME,
        endpoint=os.environ[ENDPOINT_ENV],
        namespace=os.environ.get(NAMESPACE_ENV, DEFAULT_NAMESPACE),
        api_key=os.environ[TOKEN_ENV],
        labels={"provider": EnvironmentProvider.KIND.value, "cluster": CLUSTER_NAME},
    )
    await _register_environment_record(details, database_url)
