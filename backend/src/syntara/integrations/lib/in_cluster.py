"""Helpers for the in-cluster Kubernetes API endpoint.

An OpenShift integration may register the cluster Automation Orchestrator
itself runs on. That cluster's only address is the in-cluster API Service,
which resolves to a private ClusterIP on every platform — and on managed
offerings even the external API hostname resolves to private load-balancer
addresses from inside the cluster — so the integration SSRF policy
auto-allows these hostnames when running inside a pod, and only then.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

# The kubelet injects KUBERNETES_SERVICE_HOST into every pod; it is the
# standard in-cluster signal and is absent in every other execution context.
_IN_CLUSTER_SIGNAL = "KUBERNETES_SERVICE_HOST"

# The spellings of the API server Service that the SSRF engine can accept.
# Both resolve to the same ClusterIP from any namespace (the two-label form
# via the pod's DNS search path). The full
# "kubernetes.default.svc.cluster.local" name is deliberately absent: the
# underlying engine rejects every hostname ending in ".svc.cluster.local" as
# Kubernetes-internal DNS, unconditionally — no allowlist can override it —
# so auto-allowing a spelling that can never pass would be misleading. The
# bare "kubernetes" name resolves only inside the "default" namespace and is
# excluded for the same honesty: it is not reachable where AO runs.
IN_CLUSTER_KUBERNETES_API_HOSTS = frozenset(
    {
        "kubernetes.default.svc",
        "kubernetes.default",
    }
)

# The CA bundle the kubelet mounts for the in-cluster API's serving
# certificate, signed by the cluster's service-network signer.
_SERVICE_ACCOUNT_CA = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")


def in_cluster_kubernetes_api_hosts() -> frozenset[str]:
    """Return the in-cluster API hostnames, or an empty set outside a cluster.

    Read from the environment on every call so callers cannot outlive a
    change of context (and tests can pin it).
    """
    if _IN_CLUSTER_SIGNAL not in os.environ:
        return frozenset()
    return IN_CLUSTER_KUBERNETES_API_HOSTS


def is_in_cluster_kubernetes_api_url(url: str) -> bool:
    """Return True if *url* targets the in-cluster Kubernetes API.

    Port and letter case are ignored, matching hostname comparisons in the
    SSRF policy; suffix and lookalike hosts never match.
    """
    if _IN_CLUSTER_SIGNAL not in os.environ:
        return False
    hostname = (urlparse(url).hostname or "").lower()
    return hostname in IN_CLUSTER_KUBERNETES_API_HOSTS


def service_account_ca_certificate() -> str | None:
    """Return the pod's CA bundle for the in-cluster API, or None when absent.

    Callers fall back to the system trust store when the bundle cannot be
    read, preserving the pre-existing verification behaviour.
    """
    try:
        return _SERVICE_ACCOUNT_CA.read_text()
    except OSError:
        return None
