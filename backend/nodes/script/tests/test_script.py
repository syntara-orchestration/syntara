"""Script process isolation, limits and output parity."""

from syntara_node_runtime.runtime import Invocation, execute
from syntara_node_script import Node


def run(code, **kwargs):
    return execute(Node(), Invocation(inputs={"language": "python", "code": code}, **kwargs), lambda _frame: None)


def test_last_json_line():
    assert run('print("log"); print(\'{"value": 5}\')')["result"]["Result"]["stdout_json"] == {"value": 5}


def test_timeout():
    frame = run("import time; time.sleep(30)", timeout_seconds=1)
    assert frame["error"]["type"] == "TimeoutError"


def test_output_limit():
    frame = run('print("x"*10000)', max_output_bytes=64)
    assert len(frame["result"]["Result"]["stdout"]) <= 64
    assert "truncated" in frame["result"]["Result"]["stderr"]


def test_catalog_maximum_output_limit_is_supported():
    frame = run('print("small output")', max_output_bytes=2_097_152)
    assert frame["result"]["StatusCode"] == 0
    assert frame["result"]["Result"]["stdout"] == "small output\n"


def test_parent_secret_not_in_environment(monkeypatch):
    monkeypatch.setenv("CONTROL_PLANE_SECRET", "never-export-this")
    frame = run('import os; print(os.environ.get("CONTROL_PLANE_SECRET", "absent"))')
    assert frame["result"]["Result"]["stdout"] == "absent\n"
