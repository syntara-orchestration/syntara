# ruff: noqa: TRY301
"""One pod and one gRPC invocation over an authenticated Kubernetes port-forward."""

from __future__ import annotations

import hashlib
import tempfile
import time
from contextlib import suppress
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import grpc
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import portforward
from syntara_node_protocol.client import NodeRpcError, invoke
from syntara_node_protocol.codec import CHANNEL_OPTIONS, MAX_MESSAGE_BYTES, PORT, encode_request

from syntara.workflows.node_containers.forward import forward_socket

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable

MAX_FRAME_BYTES = MAX_MESSAGE_BYTES


class TransportError(Exception):
    """Failure with an explicit safe-to-retry classification."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        """Initialize the node contract and execution state."""
        super().__init__(message)
        self.retryable = retryable


def pod_body(
    name: str, image: str, invocation: dict[str, Any], *, startup: int, grace: int, tls_secret: str | None = None
) -> dict[str, Any]:
    """Never put invocation data or cluster credentials into the pod specification."""
    volumes: list[dict[str, Any]] = [{"name": "tmp", "emptyDir": {"medium": "Memory", "sizeLimit": "64Mi"}}]
    mounts: list[dict[str, Any]] = [{"name": "tmp", "mountPath": "/tmp"}]  # noqa: S108 - isolated memory-backed pod volume
    if tls_secret:
        volumes.append({"name": "agent-tls", "secret": {"secretName": tls_secret}})
        mounts.append({"name": "agent-tls", "mountPath": "/run/agent-tls", "readOnly": True})
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": name,
            "labels": {"app.kubernetes.io/name": "syntara-node", "syntara.io/temporary-executor": "true"},
        },
        "spec": {
            "restartPolicy": "Never",
            "automountServiceAccountToken": False,
            "activeDeadlineSeconds": startup + invocation["timeout_seconds"] + grace,
            "terminationGracePeriodSeconds": grace,
            "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
            "volumes": volumes,
            "containers": [
                {
                    "name": "node",
                    "image": image,
                    "ports": [{"name": "grpc", "containerPort": PORT}],
                    "volumeMounts": mounts,
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "1", "memory": "512Mi"},
                    },
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {"drop": ["ALL"]},
                    },
                }
            ],
        },
    }


def run_pod(  # noqa: C901, PLR0912, PLR0915 - single owned pod lifecycle
    *,
    target: dict[str, Any],
    image: str,
    invocation: dict[str, Any],
    identity: str,
    startup: int,
    grace: int,
    cancelled: threading.Event,
    progress: Callable[[dict[str, Any]], None],
    tls_secret: str | None = None,
) -> dict[str, Any]:
    """Execute once; port-forward is only the network path for the gRPC channel."""
    name = "syntara-node-" + hashlib.sha256(identity.encode()).hexdigest()[:32]
    namespace = target["namespace"]
    request = encode_request(invocation, identity)
    if request.ByteSize() > MAX_FRAME_BYTES:
        message = "Node invocation exceeds transport limit"
        raise TransportError(message)
    with tempfile.TemporaryDirectory(prefix="syntara-node-") as directory:
        config = client.Configuration()
        config.host = target["base_url"]
        config.api_key["authorization"] = target["token"]
        config.api_key_prefix["authorization"] = "Bearer"
        config.verify_ssl = True
        if target.get("ca_certificate"):
            ca = Path(directory) / "ca.pem"
            ca.write_text(target["ca_certificate"])
            config.ssl_ca_cert = str(ca)
        with client.ApiClient(config) as api_client:
            api = client.CoreV1Api(api_client)
            created = False
            submitted = False
            connection = None
            try:
                api.create_namespaced_pod(
                    namespace,
                    pod_body(name, image, invocation, startup=startup, grace=grace, tls_secret=tls_secret),
                    _request_timeout=15,
                )
                created = True
                deadline = time.monotonic() + startup
                while True:
                    if cancelled.is_set():
                        message = "Node execution cancelled"
                        raise TransportError(message)
                    pod = cast("client.V1Pod", api.read_namespaced_pod(name, namespace, _request_timeout=15))
                    phase = pod.status.phase if pod.status else None
                    if phase == "Running":
                        break
                    if phase in ("Failed", "Succeeded") or time.monotonic() >= deadline:
                        message = "Node pod did not become ready"
                        raise TransportError(message, retryable=True)
                    time.sleep(0.25)
                while True:
                    connection = portforward(
                        api.connect_get_namespaced_pod_portforward,
                        name,
                        namespace,
                        ports=str(PORT),
                        _request_timeout=15,
                    )
                    try:
                        with (
                            forward_socket(connection.socket(PORT)) as address,
                            grpc.insecure_channel(address, options=CHANNEL_OPTIONS) as channel,
                        ):
                            submitted = True
                            return invoke(
                                channel,
                                invocation,
                                identity=identity,
                                progress=progress,
                                cancelled=cancelled,
                                startup=min(2, max(0.1, deadline - time.monotonic())),
                                grace=grace,
                            )
                    except NodeRpcError as exc:
                        # Running can precede the listener. A refused kubelet
                        # connection needs a new port-forward, before Execute only.
                        if not exc.retryable or time.monotonic() >= deadline:
                            raise
                        submitted = False
                        cancelled.wait(0.1)
                    finally:
                        with suppress(Exception):
                            connection.close()
                        connection = None
            except NodeRpcError as exc:
                raise TransportError(str(exc), retryable=exc.retryable) from None
            except TransportError:
                raise
            except ApiException as exc:
                message = "OpenShift request failed"
                raise TransportError(message, retryable=not submitted and exc.status in {429, 502, 503, 504}) from None
            except Exception:  # noqa: BLE001 - never expose raw API credentials or responses
                message = "Node transport failed"
                raise TransportError(message, retryable=False) from None
            finally:
                if connection is not None:
                    with suppress(Exception):
                        connection.close()
                if created:
                    try:
                        api.delete_namespaced_pod(name, namespace, grace_period_seconds=grace, _request_timeout=15)
                    except ApiException as exc:
                        if exc.status != HTTPStatus.NOT_FOUND:
                            progress(
                                {"version": 1, "kind": "progress", "event": "cleanup_failed", "data": {"pod": name}}
                            )
                    except Exception:  # noqa: BLE001 - cleanup must not hide the execution result
                        progress({"version": 1, "kind": "progress", "event": "cleanup_failed", "data": {"pod": name}})
