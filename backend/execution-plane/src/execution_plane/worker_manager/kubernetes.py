"""Cold-start Kubernetes worker provisioning and JSONL exec transport."""

# Validation failures use one domain exception with precise messages; constructing
# those messages at each validation site is clearer than dozens of tiny subclasses.
# ruff: noqa: EM101, EM102, TRY003

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog
from kubernetes import client, config
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream

from execution_plane.worker_manager.base import WorkerDispatchError

if TYPE_CHECKING:
    from collections.abc import Callable

    from execution_plane.models.execution_target import ExecutionTarget
    from execution_plane.models.work_item import WorkItem

logger = structlog.stdlib.get_logger(__name__)

MAX_EXEC_OUTPUT_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 3600
HTTP_NOT_FOUND = 404


@dataclass(frozen=True)
class WorkerTask:
    """Validated cold-start task definition stored in a WorkItem payload."""

    image: str
    pod_command: list[str] | None
    command: list[str]
    input_payload: dict[str, Any]
    timeout_seconds: int
    image_pull_policy: str

    @classmethod
    def from_work_item(cls, item: WorkItem) -> WorkerTask:
        """Parse the external task definition without accepting shell command strings."""
        raw = item.payload.get("task_definition")
        if not isinstance(raw, dict):
            raise WorkerDispatchError("work item has no task_definition object")
        image = raw.get("image")
        pod_command = raw.get("pod_command")
        command = raw.get("command")
        input_payload = raw.get("input")
        timeout = raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        pull_policy = raw.get("image_pull_policy", "IfNotPresent")
        if not isinstance(image, str) or not image.strip():
            raise WorkerDispatchError("task_definition.image must be a non-empty string")
        if pod_command is not None and (
            not isinstance(pod_command, list)
            or not pod_command
            or not all(isinstance(part, str) and part for part in pod_command)
        ):
            raise WorkerDispatchError("task_definition.pod_command must be a non-empty string array")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise WorkerDispatchError("task_definition.command must be a non-empty string array")
        if not isinstance(input_payload, dict):
            raise WorkerDispatchError("task_definition.input must be an object")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
            raise WorkerDispatchError("task_definition.timeout_seconds must be between 1 and 3600")
        if pull_policy not in {"Always", "IfNotPresent", "Never"}:
            raise WorkerDispatchError("task_definition.image_pull_policy is invalid")
        return cls(image.strip(), pod_command, command, input_payload, timeout, pull_policy)


class KubernetesWorkerManager:
    """Provision one hardened pod per work item, exec JSONL, then delete it."""

    def __init__(
        self,
        target: ExecutionTarget,
        *,
        api_client_factory: Callable[[], ApiClient] | None = None,
    ) -> None:
        """Configure a target; credentials are resolved only when dispatch begins."""
        self._target = target
        self._api_client_factory = api_client_factory or self._build_api_client

    async def dispatch(self, work_item: WorkItem) -> dict[str, Any]:
        """Run the blocking Kubernetes websocket client outside the event loop."""
        task = WorkerTask.from_work_item(work_item)
        return await asyncio.to_thread(self._dispatch_sync, work_item, task)

    def build_pod(self, work_item: WorkItem, task: WorkerTask) -> client.V1Pod:
        """Build an OpenShift-restricted-compatible ephemeral worker pod."""
        security_context = client.V1SecurityContext(
            allow_privilege_escalation=False,
            capabilities=client.V1Capabilities(drop=["ALL"]),
            read_only_root_filesystem=True,
            run_as_non_root=True,
            seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
        )
        container = client.V1Container(
            name="worker",
            image=task.image,
            image_pull_policy=task.image_pull_policy,
            command=task.pod_command,
            stdin=True,
            tty=False,
            security_context=security_context,
            resources=client.V1ResourceRequirements(
                requests={"cpu": "25m", "memory": "64Mi"},
                limits={"cpu": "1", "memory": "512Mi"},
            ),
            volume_mounts=[client.V1VolumeMount(name="tmp", mount_path="/tmp")],  # noqa: S108
        )
        return client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=self._pod_name(work_item),
                labels={
                    "app.kubernetes.io/name": "syntara-ep-worker",
                    "app.kubernetes.io/managed-by": "execution-plane",
                    "syntara.io/work-item-id": str(work_item.id),
                },
            ),
            spec=client.V1PodSpec(
                automount_service_account_token=False,
                containers=[container],
                enable_service_links=False,
                restart_policy="Never",
                termination_grace_period_seconds=1,
                volumes=[client.V1Volume(name="tmp", empty_dir=client.V1EmptyDirVolumeSource(size_limit="64Mi"))],
            ),
        )

    def _dispatch_sync(self, work_item: WorkItem, task: WorkerTask) -> dict[str, Any]:
        pod = self.build_pod(work_item, task)
        metadata = pod.metadata
        if metadata is None or not metadata.name:
            raise WorkerDispatchError("generated pod has no name")
        pod_name = metadata.name
        api_client = self._api_client_factory()
        core = client.CoreV1Api(api_client)
        created = False
        try:
            core.create_namespaced_pod(namespace=self._target.namespace, body=pod)
            created = True
            logger.info(
                "Created cold-start worker pod",
                work_item_id=str(work_item.id),
                pod=pod_name,
                namespace=self._target.namespace,
            )
            self._wait_until_running(core, pod_name, task.timeout_seconds)
            result = self._exec_json(core, pod_name, task)
            if result.get("ok") is False and not work_item.payload.get("workflow_node_type"):
                message = result.get("message", "worker returned an unsuccessful result")
                raise WorkerDispatchError(str(message))
            return {
                "request_id": task.input_payload.get("request_id", str(work_item.id)),
                "status": "completed",
                "result": result,
                "worker_pod": pod_name,
                "worker_namespace": self._target.namespace,
            }
        except ApiException as exc:
            raise WorkerDispatchError(f"Kubernetes API request failed: {exc.reason}") from exc
        finally:
            if created:
                self._delete_pod(core, pod_name)
            api_client.close()

    def _wait_until_running(self, core: client.CoreV1Api, pod_name: str, timeout_seconds: int) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            pod = cast(
                "client.V1Pod",
                core.read_namespaced_pod(name=pod_name, namespace=self._target.namespace),
            )
            status = cast("client.V1PodStatus | None", pod.status)
            phase = status.phase if status else None
            if phase == "Running":
                return
            if phase in {"Failed", "Succeeded"}:
                reason = status.reason if status else None
                raise WorkerDispatchError(f"worker pod entered terminal phase {phase}: {reason or 'unknown reason'}")
            time.sleep(0.5)
        raise WorkerDispatchError(f"worker pod did not become running within {timeout_seconds}s")

    def _exec_json(self, core: client.CoreV1Api, pod_name: str, task: WorkerTask) -> dict[str, Any]:
        ws = stream(
            core.connect_get_namespaced_pod_exec,
            pod_name,
            self._target.namespace,
            command=task.command,
            container="worker",
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False,
        )
        stdout_buffer = ""
        stderr = ""
        output_bytes = 0
        deadline = time.monotonic() + task.timeout_seconds
        try:
            ws.write_stdin(json.dumps(task.input_payload, separators=(",", ":"), allow_nan=False) + "\n")
            while time.monotonic() < deadline and ws.is_open():
                ws.update(timeout=min(1.0, max(0.0, deadline - time.monotonic())))
                if ws.peek_stdout():
                    chunk = ws.read_stdout()
                    stdout_buffer += chunk
                    output_bytes += len(chunk.encode())
                if ws.peek_stderr():
                    chunk = ws.read_stderr()
                    stderr += chunk
                    output_bytes += len(chunk.encode())
                if output_bytes > MAX_EXEC_OUTPUT_BYTES:
                    raise WorkerDispatchError("worker output exceeded 2 MiB")
                while "\n" in stdout_buffer:
                    line, _, stdout_buffer = stdout_buffer.partition("\n")
                    if not line.strip():
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise WorkerDispatchError("worker stdout was not valid JSONL") from exc
                    if not isinstance(value, dict):
                        raise WorkerDispatchError("worker response must be a JSON object")
                    return value
            detail = stderr.strip() or "no output"
            raise WorkerDispatchError(f"worker produced no JSON response: {detail}")
        finally:
            ws.close()

    def _delete_pod(self, core: client.CoreV1Api, pod_name: str) -> None:
        try:
            core.delete_namespaced_pod(
                name=pod_name,
                namespace=self._target.namespace,
                body=client.V1DeleteOptions(grace_period_seconds=0, propagation_policy="Background"),
            )
            logger.info("Deleted cold-start worker pod", pod=pod_name, namespace=self._target.namespace)
        except ApiException as exc:
            if exc.status != HTTP_NOT_FOUND:
                logger.exception("Failed to delete cold-start worker pod", pod=pod_name)

    def _build_api_client(self) -> ApiClient:
        credential = self._target.credential_ref
        credential_type = credential.get("type")
        if credential_type == "kubeconfig":
            configuration = client.Configuration()
            config.load_kube_config(
                config_file=str(credential.get("path")),
                context=credential.get("context"),
                client_configuration=configuration,
            )
            return ApiClient(configuration)
        if credential_type == "in_cluster":
            config.load_incluster_config()
            return ApiClient()
        configuration = client.Configuration()
        configuration.host = self._target.endpoint.rstrip("/")
        configuration.verify_ssl = bool(credential.get("verify_ssl", True))
        ca_path = credential.get("ca_path")
        if isinstance(ca_path, str) and ca_path:
            configuration.ssl_ca_cert = ca_path
        token = self._read_bearer_token(credential)
        # kubernetes-client 36 renamed the generated auth key to BearerToken.
        # Its legacy "authorization" alias does not apply the alias's prefix,
        # which silently produces an anonymous request if used here.
        configuration.api_key["BearerToken"] = token
        configuration.api_key_prefix["BearerToken"] = "Bearer"
        return ApiClient(configuration)

    @staticmethod
    def _read_bearer_token(credential: dict[str, Any]) -> str:
        credential_type = credential.get("type")
        if credential_type == "file":
            path = credential.get("path")
            if not isinstance(path, str) or not path:
                raise WorkerDispatchError("credential_ref file path is missing")
            token = Path(path).read_text().strip()
        elif credential_type == "env":
            name = credential.get("name")
            if not isinstance(name, str) or not name:
                raise WorkerDispatchError("credential_ref environment variable name is missing")
            token = os.environ.get(name, "").strip()
        else:
            raise WorkerDispatchError(f"unsupported credential_ref type: {credential_type}")
        if not token:
            raise WorkerDispatchError("Kubernetes bearer token is empty")
        return token

    @staticmethod
    def _pod_name(item: WorkItem) -> str:
        return f"ep-{item.id.hex[:20]}"
