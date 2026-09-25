"""Image responses preserve existing Temporal node output and failure contracts."""

import pytest
from execution_plane.workflow_result import WorkflowResultError, normalize_workflow_result


def test_http_response_maps_nested_body() -> None:
    response = {
        "result": {
            "ok": True,
            "status_code": 200,
            "body": {"name": "dynamic"},
            "headers": {"content-type": "application/json"},
            "elapsed": 0.2,
        }
    }

    result = normalize_workflow_result("http_request", response, {"name": "${result.body.name}"})

    assert result == {"output": {"name": "dynamic"}}


def test_http_retryable_failure_keeps_mapped_output() -> None:
    response = {"result": {"ok": False, "status_code": 503, "body": "unavailable", "message": "HTTP 503"}}

    with pytest.raises(WorkflowResultError) as exc_info:
        normalize_workflow_result("http_request", response, None)

    assert exc_info.value.error_type == "HTTPError"
    assert exc_info.value.non_retryable is False
    assert exc_info.value.details == {
        "output": {"status_code": 503, "body": "unavailable", "headers": None, "elapsed": None}
    }


def test_script_response_parses_last_json_line() -> None:
    response = {"result": {"ok": True, "return_code": 0, "stdout": 'progress\n{"value":42}\n', "stderr": ""}}

    result = normalize_workflow_result("script", response, {"value": "${result.stdout_json.value}"})

    assert result == {"output": {"value": 42}}


def test_script_failure_is_not_reported_as_success() -> None:
    with pytest.raises(WorkflowResultError) as exc_info:
        normalize_workflow_result(
            "script", {"result": {"ok": False, "message": "script failed with exit code 1"}}, None
        )

    assert exc_info.value.error_type == "ScriptExecutionError"


def test_mapping_error_does_not_expose_worker_payload() -> None:
    with pytest.raises(WorkflowResultError) as exc_info:
        normalize_workflow_result(
            "http_request",
            {"result": {"ok": True, "body": {"secret": "never-print"}}},
            {"missing": "${result.body.nonexistent}"},
        )

    assert "never-print" not in str(exc_info.value)
