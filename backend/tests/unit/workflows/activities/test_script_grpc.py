"""Exercise the SDK client against a real local gRPC server, without a cluster."""

import asyncio
import json
from collections.abc import AsyncIterator
from unittest.mock import patch

import grpc
import pytest
from syntara_plugin.runtime import ContainerInvocation
from syntara_plugin.runtime.protocol import container_pb2 as pb
from syntara_plugin.runtime.protocol import container_pb2_grpc as rpc
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.script_grpc import SCRIPT_STEP_IDS, invoke_script


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "nonzero",
        "structured_nonzero",
        "structured_timeout",
        "structured_invalid",
        "failure",
        "bad_abi",
        "bad_identity",
        "no_result",
        "timeout",
        "cancel",
        "wrong_step",
        "duplicate_result",
    ],
)
async def test_script_protocol(scenario):  # noqa: C901 -- shared real server exercises the protocol outcome matrix
    started = asyncio.Event()
    cancelled = asyncio.Event()
    observed = []

    class Service(rpc.ContainerServiceServicer):
        async def Health(self, request: pb.HealthRequest, context: object) -> pb.HealthResponse:  # noqa: N802
            return pb.HealthResponse(
                ready=True,
                runtime_abi="wrong" if scenario == "bad_abi" else "syntara.container/v1alpha1",
                step_revision_ids=["other.step"] if scenario == "wrong_step" else [SCRIPT_STEP_IDS["python"]],
            )

        async def Execute(self, request: pb.ExecuteRequest, context: object) -> AsyncIterator[pb.ExecutionEvent]:  # noqa: N802
            observed.append(request)
            started.set()
            if scenario in {"timeout", "cancel"}:
                await cancelled.wait()
            if scenario == "no_result":
                return
            if scenario == "failure":
                yield pb.ExecutionEvent(
                    invocation_id=request.invocation_id,
                    failure=pb.Failure(
                        code="REMOTE_REJECTED",
                        retryable=False,
                        outcome="not_completed",
                    ),
                )
                return
            if scenario.startswith("structured_"):
                error = {
                    "message": "Script failed",
                    "code": "TIMEOUT" if scenario == "structured_timeout" else "REMOTE_REJECTED",
                    "category": "timeout" if scenario == "structured_timeout" else "business",
                    "retryable": False,
                    "return_code": 7,
                    "stdout": "hello",
                    "stderr": "error",
                }
                if scenario == "structured_invalid":
                    del error["return_code"]
                yield pb.ExecutionEvent(
                    invocation_id=request.invocation_id,
                    result=pb.Result(
                        output_schema_digest="sha256:" + "a" * 64,
                        status_code=1,
                        status_message="Script failed",
                        error_schema_digest="sha256:" + "b" * 64,
                        error_result_json=json.dumps(error).encode(),
                    ),
                )
                return
            output = {"return_code": 7 if scenario == "nonzero" else 0, "stdout": "hello", "stderr": "error"}
            event = pb.ExecutionEvent(
                invocation_id="wrong" if scenario == "bad_identity" else request.invocation_id,
                result=pb.Result(output_schema_digest="sha256:" + "a" * 64, output_json=json.dumps(output).encode()),
            )

            yield event
            if scenario == "duplicate_result":
                yield event

        async def Cancel(self, request: pb.CancelRequest, context: object) -> pb.CancelResponse:  # noqa: N802
            cancelled.set()
            return pb.CancelResponse(accepted=True)

    server = grpc.aio.server()
    rpc.add_ContainerServiceServicer_to_server(Service(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    invocation = ContainerInvocation(
        invocation_id="script-test",
        workflow_run_id="run-test",
        step_revision_id=SCRIPT_STEP_IDS["python"],
        inputs={"code": "print(1)", "environment": {"LARGE_VALUE": "x" * 150_000}},
        credential_file_paths={},
        timeout_seconds=1 if scenario == "timeout" else 5,
    )
    try:
        with patch("temporalio.activity.heartbeat"):
            task = asyncio.create_task(invoke_script(f"127.0.0.1:{port}", invocation))
            if scenario == "cancel":
                await asyncio.wait_for(started.wait(), 5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert cancelled.is_set()
            elif scenario in {"timeout", "structured_timeout"}:
                with pytest.raises(TimeoutError):
                    await task
                assert cancelled.is_set()
            elif scenario in {
                "failure",
                "bad_abi",
                "bad_identity",
                "no_result",
                "wrong_step",
                "duplicate_result",
                "structured_invalid",
            }:
                with pytest.raises(ApplicationError):
                    await task
            else:
                output = await task
                assert output["return_code"] == (7 if scenario in {"nonzero", "structured_nonzero"} else 0)
                assert output["stdout"] == "hello"
                assert observed[0].timeout_seconds == 5
                assert json.loads(observed[0].inputs_json) == invocation.inputs
    finally:
        await server.stop(0)
