"""Disposable pod lifecycle and uncertain-delivery behavior."""

import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from syntara_node_protocol.client import NodeRpcError

from syntara.workflows.node_containers.transport import TransportError, pod_body, run_pod

INVOCATION = {
    "version": 1,
    "inputs": {"url": "https://example.com"},
    "credentials": {"token": "do-not-store"},
    "timeout_seconds": 30,
}
FRAME = {"version": 1, "kind": "result", "result": {"Result": {"status_code": 200}, "StatusCode": 0}, "error": None}


def test_pod_never_contains_credentials():
    pod = pod_body("test", "node@sha256:123", INVOCATION, startup=120, grace=30)
    assert "do-not-store" not in json.dumps(pod)
    assert pod["spec"]["automountServiceAccountToken"] is False
    assert pod["spec"]["restartPolicy"] == "Never"
    assert "stdin" not in pod["spec"]["containers"][0]
    assert pod["spec"]["containers"][0]["ports"][0]["containerPort"] == 50051
    assert pod["spec"]["containers"][0]["securityContext"]["readOnlyRootFilesystem"] is True


@pytest.mark.parametrize("success", [True, False])
def test_grpc_once_cleanup(success):
    api = MagicMock()
    api.read_namespaced_pod.return_value = SimpleNamespace(status=SimpleNamespace(phase="Running"))
    connection = MagicMock()
    with (
        patch("syntara.workflows.node_containers.transport.client.CoreV1Api", return_value=api),
        patch("syntara.workflows.node_containers.transport.portforward", return_value=connection),
        patch("syntara.workflows.node_containers.transport.forward_socket") as forward,
        patch("syntara.workflows.node_containers.transport.invoke") as invoke,
    ):
        forward.return_value.__enter__.return_value = "127.0.0.1:50051"
        invoke.return_value = FRAME
        if not success:
            invoke.side_effect = NodeRpcError("Disconnected after submission")
        args = dict(  # noqa: C408 - explicit keyword argument bundle
            target={"namespace": "nodes", "base_url": "https://cluster.example", "token": "cluster-secret"},
            image="node:test",
            invocation=INVOCATION,
            identity="unique",
            startup=1,
            grace=10,
            cancelled=threading.Event(),
            progress=lambda _frame: None,
        )
        if success:
            assert run_pod(**args) == FRAME
        else:
            with pytest.raises(TransportError) as error:
                run_pod(**args)
            assert error.value.retryable is False
    assert api.create_namespaced_pod.call_count == 1
    assert invoke.call_count == 1
    assert api.delete_namespaced_pod.call_count == 1
    assert "cluster-secret" not in json.dumps(invoke.call_args.args[1])
    connection.close.assert_called_once()


def test_cancel_before_submission():
    api = MagicMock()
    cancelled = threading.Event()
    cancelled.set()
    with (
        patch("syntara.workflows.node_containers.transport.client.CoreV1Api", return_value=api),
        patch("syntara.workflows.node_containers.transport.portforward") as forward,
    ):
        with pytest.raises(TransportError):
            run_pod(
                target={"namespace": "nodes", "base_url": "https://cluster.example", "token": "cluster-secret"},
                image="node:test",
                invocation=INVOCATION,
                identity="unique",
                startup=1,
                grace=10,
                cancelled=cancelled,
                progress=lambda _frame: None,
            )
    forward.assert_not_called()
    api.delete_namespaced_pod.assert_called_once()


def test_listener_startup_reconnects_without_recreating_pod():
    api = MagicMock()
    api.read_namespaced_pod.return_value = SimpleNamespace(status=SimpleNamespace(phase="Running"))
    with (
        patch("syntara.workflows.node_containers.transport.client.CoreV1Api", return_value=api),
        patch("syntara.workflows.node_containers.transport.portforward") as portforward,
        patch("syntara.workflows.node_containers.transport.forward_socket") as forward,
        patch("syntara.workflows.node_containers.transport.invoke") as invoke,
    ):
        forward.return_value.__enter__.return_value = "127.0.0.1:50051"
        invoke.side_effect = [NodeRpcError("Not listening yet", retryable=True), FRAME]
        assert (
            run_pod(
                target={"namespace": "nodes", "base_url": "https://cluster.example", "token": "cluster-secret"},
                image="node:test",
                invocation=INVOCATION,
                identity="unique",
                startup=5,
                grace=10,
                cancelled=threading.Event(),
                progress=lambda _frame: None,
            )
            == FRAME
        )
    assert api.create_namespaced_pod.call_count == 1
    assert api.delete_namespaced_pod.call_count == 1
    assert portforward.call_count == 2
    assert portforward.return_value.close.call_count == 2
