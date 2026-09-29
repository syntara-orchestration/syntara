"""SDK result translation preserves the workflow-visible contract."""

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.node_containers.dispatch import map_result


def test_output_expression_and_suppression():
    frame = {"result": {"StatusCode": 0, "Result": {"body": {"value": 42}, "status_code": 200}}}
    assert map_result(frame, {"answer": "${result.body.value}"}, "http_request") == {"output": {"answer": 42}}
    assert map_result(frame, {}, "http_request") == {"output": {}}


def test_script_keeps_existing_ep_field_selection():
    frame = {"result": {"StatusCode": 0, "Result": {"stdout": "hello", "return_code": 0}}}
    assert map_result(frame, {"stdout": "ignored"}, "script") == {"output": {"stdout": "hello"}}


def test_partial_failure_and_retry():
    frame = {
        "result": {"StatusCode": 1, "Result": {"status_code": 503}, "ErrorMessage": "HTTP failed"},
        "error": {"type": "HTTPError", "retryable": True},
    }
    with pytest.raises(ApplicationError) as error:
        map_result(frame, None, "http_request")
    assert error.value.non_retryable is False
    assert error.value.type == "HTTPError"
    assert error.value.details == ({"output": {"status_code": 503}},)


@pytest.mark.parametrize(
    "frame", [{}, {"result": {"StatusCode": True}}, {"result": {"StatusCode": 0, "Result": "bad"}}]
)
def test_invalid_contract_is_not_retryable(frame):
    with pytest.raises(ApplicationError) as error:
        map_result(frame, None, "http_request")
    assert error.value.non_retryable
