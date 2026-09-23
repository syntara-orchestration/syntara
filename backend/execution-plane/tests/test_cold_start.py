"""Live OpenShift cold-start validation.

This test is skipped unless its explicit EP_E2E_* environment is present. It
submits through the Syntara-hosted EP API, observes the work-item-labelled pod,
waits for terminal persistence, then verifies cleanup.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any

import asyncpg
import httpx
import pytest
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

HTTP_NOT_FOUND = 404
_HTTP_EXEC_CODE = """\
import json
import sys
import urllib.request

wire = json.loads(sys.stdin.readline())
request = wire["input"]
http_request = urllib.request.Request(
    request["url"],
    method=request.get("method", "GET"),
    headers={"User-Agent": "syntara-execution-plane-e2e"},
)
with urllib.request.urlopen(http_request, timeout=30) as response:
    body = response.read(1048576).decode("utf-8", errors="replace")
    print(json.dumps({"ok": True, "status_code": response.status, "body": body}), flush=True)
"""


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for the live cold-start test")
    return value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cold_start_pod_exec_and_cleanup() -> None:
    """Exercise POST /submit through OpenShift pod exec and DB completion."""
    api_url = _required_environment("EP_E2E_API_URL").rstrip("/")
    database_url = _required_environment("EP_E2E_DATABASE_URL").replace("postgresql+asyncpg://", "postgresql://")
    api_token = _required_environment("EP_E2E_API_TOKEN")
    kubeconfig = _required_environment("EP_E2E_KUBECONFIG")
    namespace = os.environ.get("EP_E2E_NAMESPACE", "ep-dev-workers")
    image = os.environ.get("EP_E2E_WORKER_IMAGE", "registry.access.redhat.com/ubi9/python-312:latest")
    command_override = os.environ.get("EP_E2E_WORKER_COMMAND")
    command = command_override.split(",") if command_override else ["python", "-c", _HTTP_EXEC_CODE]
    request_id = f"exec-{uuid.uuid4()}"

    submission = {
        "target_selector": {
            "environment": "development",
            "execution-mode": "cold-start",
            "platform": "openshift",
        },
        "task_definition": {
            "image": image,
            "pod_command": ["/bin/sh", "-c", "trap : TERM INT; sleep infinity & wait"],
            "command": command,
            "input": {
                "request_id": request_id,
                "workflow_id": f"wf-{uuid.uuid4()}",
                "input": {"method": "GET", "url": "https://api.github.com"},
            },
            "timeout_seconds": 120,
            "image_pull_policy": "Always",
        },
    }
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(
            f"{api_url}/api/execution_plane/v1/submit",
            json=submission,
            headers={"Authorization": f"Bearer {api_token}"},
        )
    response.raise_for_status()
    work_item_id = response.json()["id"]

    configuration = client.Configuration()
    config.load_kube_config(config_file=kubeconfig, client_configuration=configuration)
    core = client.CoreV1Api(client.ApiClient(configuration))
    selector = f"syntara.io/work-item-id={work_item_id}"
    observed_pod = await asyncio.to_thread(_wait_for_pod, core, namespace, selector, 60)
    assert observed_pod.metadata.labels["syntara.io/work-item-id"] == work_item_id

    row = await _wait_for_terminal(database_url, work_item_id, 180)
    assert row["status"] == "completed"
    result: dict[str, Any] = row["result"]
    assert result["request_id"] == request_id
    assert result["status"] == "completed"
    assert result["result"]["ok"] is True

    await asyncio.to_thread(_wait_for_pod_deletion, core, namespace, observed_pod.metadata.name, 60)


def _wait_for_pod(core: client.CoreV1Api, namespace: str, selector: str, timeout: int) -> client.V1Pod:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pods = core.list_namespaced_pod(namespace=namespace, label_selector=selector).items
        if pods:
            return pods[0]
        time.sleep(0.25)
    pytest.fail("cold-start worker pod was not observed")


def _wait_for_pod_deletion(core: client.CoreV1Api, namespace: str, name: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            core.read_namespaced_pod(namespace=namespace, name=name)
        except ApiException as exc:
            if exc.status == HTTP_NOT_FOUND:
                return
            raise
        time.sleep(0.25)
    pytest.fail("cold-start worker pod was not deleted")


async def _wait_for_terminal(database_url: str, work_item_id: str, timeout_seconds: int) -> asyncpg.Record:
    deadline = time.monotonic() + timeout_seconds
    connection = await asyncpg.connect(database_url)
    try:
        while time.monotonic() < deadline:
            row = await connection.fetchrow(
                "SELECT status, result FROM execution_plane.work_items WHERE id = $1",
                uuid.UUID(work_item_id),
            )
            if row and row["status"] in {"completed", "failed"}:
                return row
            await asyncio.sleep(0.25)
    finally:
        await connection.close()
    pytest.fail("work item did not reach a terminal state")
