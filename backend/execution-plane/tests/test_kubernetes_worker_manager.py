"""Tests for cold-start Kubernetes pod construction and lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus
from execution_plane.models.work_item import WorkItem, WorkItemStatus
from execution_plane.worker_manager.base import WorkerDispatchError
from execution_plane.worker_manager.kubernetes import KubernetesWorkerManager, WorkerTask
from kubernetes import client


def _target() -> ExecutionTarget:
    return ExecutionTarget(
        id=uuid.uuid4(),
        name="dev-openshift-cluster",
        backend_type=BackendType.VANILLA_K8S,
        endpoint="https://api.example.test:6443",
        namespace="ep-dev-workers",
        credential_ref={"type": "env", "name": "TEST_TOKEN"},
        status=TargetStatus.ACTIVE,
        enabled=True,
        labels={"environment": "development"},
        created_at=datetime.now(UTC),
    )


def _work_item() -> WorkItem:
    return WorkItem(
        id=uuid.uuid4(),
        work_correlation_id=uuid.uuid4(),
        status=WorkItemStatus.CLAIMED,
        payload={
            "task_definition": {
                "image": "quay.io/example/http-executor:dev",
                "command": ["python", "-m", "syntara.http_executor"],
                "input": {"request_id": "exec-12345", "input": {"url": "https://api.github.com"}},
                "timeout_seconds": 30,
            }
        },
        created_at=datetime.now(UTC),
    )


def test_build_pod_is_hardened_for_openshift() -> None:
    item = _work_item()
    manager = KubernetesWorkerManager(_target())
    pod = manager.build_pod(item, WorkerTask.from_work_item(item))

    assert pod.metadata.namespace is None
    assert pod.metadata.labels["syntara.io/work-item-id"] == str(item.id)
    assert pod.spec.automount_service_account_token is False
    assert pod.spec.restart_policy == "Never"
    container = pod.spec.containers[0]
    assert container.stdin is True
    assert container.command is None
    assert container.security_context.run_as_non_root is True
    assert container.security_context.read_only_root_filesystem is True
    assert container.security_context.allow_privilege_escalation is False
    assert container.security_context.capabilities.drop == ["ALL"]


def test_task_definition_rejects_shell_command_string() -> None:
    item = _work_item()
    item.payload["task_definition"]["command"] = "python -m syntara.http_executor"

    with pytest.raises(WorkerDispatchError, match="string array"):
        WorkerTask.from_work_item(item)


class _FakeApiClient:
    closed = False

    def close(self) -> None:
        self.closed = True


class _FakeCoreApi:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.deleted: list[str] = []

    def create_namespaced_pod(self, namespace: str, body: client.V1Pod) -> None:
        self.created.append(f"{namespace}/{body.metadata.name}")

    def read_namespaced_pod(self, name: str, namespace: str) -> client.V1Pod:
        return client.V1Pod(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace),
            status=client.V1PodStatus(phase="Running"),
        )

    def connect_get_namespaced_pod_exec(self) -> None:
        """Only supplies the callable expected by stream()."""

    def delete_namespaced_pod(self, name: str, namespace: str, body: client.V1DeleteOptions) -> None:
        assert body.grace_period_seconds == 0
        self.deleted.append(f"{namespace}/{name}")


class _FakeWebSocket:
    def __init__(self) -> None:
        self.input = ""
        self.closed = False
        self._stdout = '{"ok":true,"status_code":200,"body":"ok"}\n'

    def write_stdin(self, value: str) -> None:
        self.input = value

    def is_open(self) -> bool:
        return not self.closed

    def update(self, timeout: float) -> None:
        assert timeout > 0

    def peek_stdout(self) -> bool:
        return bool(self._stdout)

    def read_stdout(self) -> str:
        value, self._stdout = self._stdout, ""
        return value

    def peek_stderr(self) -> bool:
        return False

    def read_stderr(self) -> str:
        return ""

    def close(self) -> None:
        self.closed = True


class _ChunkedFakeWebSocket(_FakeWebSocket):
    def __init__(self) -> None:
        super().__init__()
        response = '{"ok":true,"status_code":200,"body":"' + ("x" * 20_000) + '"}\n'
        self._chunks = [response[:100], response[100:10_000], response[10_000:]]
        self._stdout = ""

    def update(self, timeout: float) -> None:
        super().update(timeout)
        if self._chunks:
            self._stdout = self._chunks.pop(0)


def test_dispatch_streams_json_and_always_deletes_pod() -> None:
    item = _work_item()
    api_client = _FakeApiClient()
    core = _FakeCoreApi()
    websocket = _FakeWebSocket()
    manager = KubernetesWorkerManager(_target(), api_client_factory=lambda: api_client)

    with (
        patch("execution_plane.worker_manager.kubernetes.client.CoreV1Api", return_value=core),
        patch("execution_plane.worker_manager.kubernetes.stream", return_value=websocket),
    ):
        result = manager._dispatch_sync(item, WorkerTask.from_work_item(item))

    assert result["request_id"] == "exec-12345"
    assert result["status"] == "completed"
    assert result["result"]["status_code"] == 200
    assert '"request_id":"exec-12345"' in websocket.input
    assert core.created == core.deleted
    assert api_client.closed is True


def test_dispatch_waits_for_complete_jsonl_line_across_stdout_chunks() -> None:
    item = _work_item()
    api_client = _FakeApiClient()
    core = _FakeCoreApi()
    websocket = _ChunkedFakeWebSocket()
    manager = KubernetesWorkerManager(_target(), api_client_factory=lambda: api_client)

    with (
        patch("execution_plane.worker_manager.kubernetes.client.CoreV1Api", return_value=core),
        patch("execution_plane.worker_manager.kubernetes.stream", return_value=websocket),
    ):
        result = manager._dispatch_sync(item, WorkerTask.from_work_item(item))

    assert result["result"]["body"] == "x" * 20_000
    assert websocket._chunks == []
    assert core.created == core.deleted
    assert api_client.closed is True
