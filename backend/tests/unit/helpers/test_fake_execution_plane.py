"""Contract and completion behavior of the Execution Plane test double."""

import asyncio
from importlib.resources import files
from typing import Any
from uuid import UUID, uuid4

import pytest
import yaml
from jsonschema import Draft202012Validator

from tests.fixtures.fake_execution_plane import FakeExecutionPlaneHttpClient, execute_fixture_script


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "code", "stdout_json"),
    [
        ("bash", "echo step", None),
        ("bash", "echo '{\"value\": 1}'", None),
        ("python", "print('step')", None),
        ("python", "print('{\"value\": 1}')", {"value": 1}),
    ],
)
async def test_script_output_matches_plugin_contract(language: str, code: str, stdout_json: object) -> None:
    result, status = await execute_fixture_script(
        {"invocation": {"step_revision_id": f"syntara.script-{language}", "inputs": {"code": code}}}
    )
    manifest = yaml.safe_load(
        files("syntara.execution_plane.registry.manifests").joinpath(f"script-{language}.yaml").read_text()
    )
    assert status == "completed"
    Draft202012Validator(manifest["spec"]["output"]["value"]).validate(result["output"])
    if language == "python":
        assert result["output"]["stdout_json"] == stdout_json
    else:
        assert "stdout_json" not in result["output"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
async def test_callback_completion_does_not_return_a_terminal_result(status: str) -> None:
    work_item_id = uuid4()
    result = {"output": {"return_code": 0, "stdout": "step\n", "stderr": ""}}
    release_callback = asyncio.Event()
    callback_finished = asyncio.Event()
    completions: list[tuple[UUID, str, dict[str, Any]]] = []

    async def on_completion(item_id: UUID, item_status: str, item_result: dict[str, Any]) -> None:
        await release_callback.wait()
        completions.append((item_id, item_status, item_result))
        callback_finished.set()

    client = FakeExecutionPlaneHttpClient(on_completion=on_completion)
    client.work_items[work_item_id] = {"id": str(work_item_id), "status": status, "result": result}
    response = await client.get_work_item(work_item_id=work_item_id)
    try:
        assert response == {"id": str(work_item_id), "status": "running", "result": None}
        assert not completions
    finally:
        release_callback.set()
        await asyncio.wait_for(callback_finished.wait(), timeout=1)
    assert completions == [(work_item_id, status, result)]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
async def test_without_callback_returns_terminal_result(status: str) -> None:
    client = FakeExecutionPlaneHttpClient()
    work_item_id = uuid4()
    response = {"id": str(work_item_id), "status": status, "result": {"output": {}}}
    client.work_items[work_item_id] = response

    assert await client.get_work_item(work_item_id=work_item_id) == response
