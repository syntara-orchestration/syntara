"""Both AAP containers preserve launch, polling and partial-result semantics."""

import importlib

import httpx
import pytest
import respx
from syntara_node_runtime.runtime import Invocation, NodeSettings, execute


@pytest.mark.parametrize(
    ("module", "template", "jobs", "prefix"),
    [
        ("aap_job", "job_templates", "jobs", "job"),
        ("aap_workflow", "workflow_job_templates", "workflow_jobs", "workflow_job"),
    ],
)
@pytest.mark.parametrize("status", ["successful", "failed"])
@respx.mock
def test_launch_poll_result(module, template, jobs, prefix, status):
    node = importlib.import_module("syntara_node_" + module).Node()
    key = "job_template_id" if module == "aap_job" else "workflow_job_template_id"
    respx.post(f"https://aap.example/api/controller/v2/{template}/1/launch/").mock(
        return_value=httpx.Response(201, json={"id": 42})
    )
    respx.get(f"https://aap.example/api/controller/v2/{jobs}/42/").mock(
        return_value=httpx.Response(200, json={"status": status, "artifacts": {"answer": 42}})
    )
    events = []
    invocation = Invocation(
        inputs={key: 1},
        credentials={"resolved": {"extra_vars": {"aap_oauth_token": "private-token"}}},
        workflow_context={"integration": {"base_url": "https://aap.example", "verify_ssl": True}},
        settings=NodeSettings(aap_poll_interval_seconds=0.01),
    )
    frame = execute(node, invocation, events.append)
    assert frame["result"]["Result"][prefix + "_id"] == 42, frame
    assert frame["result"]["StatusCode"] == (0 if status == "successful" else 1)
    assert any(event.get("event") == "aap_launched" for event in events)
    if status == "failed":
        assert frame["error"]["retryable"] is False


@respx.mock
def test_cancellation_issues_one_remote_cancel():
    import os
    import signal

    node = importlib.import_module("syntara_node_aap_job").Node()
    respx.post("https://aap.example/api/controller/v2/job_templates/1/launch/").mock(
        return_value=httpx.Response(201, json={"id": 42})
    )
    respx.get("https://aap.example/api/controller/v2/jobs/42/").mock(
        return_value=httpx.Response(200, json={"status": "running"})
    )
    cancel = respx.post("https://aap.example/api/controller/v2/jobs/42/cancel/").mock(return_value=httpx.Response(202))

    def writer(frame) -> None:
        if frame.get("event") == "aap_launched":
            os.kill(os.getpid(), signal.SIGTERM)

    invocation = Invocation(
        inputs={"job_template_id": 1},
        credentials={"resolved": {"extra_vars": {"aap_oauth_token": "private-token"}}},
        workflow_context={"integration": {"base_url": "https://aap.example", "verify_ssl": True}},
        settings=NodeSettings(aap_poll_interval_seconds=0.01),
    )
    frame = execute(node, invocation, writer)
    assert frame["error"]["type"] == "CancelledError"
    assert cancel.call_count == 1
    assert frame["result"]["Result"]["job_id"] == 42
