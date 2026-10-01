"""Translate protobuf messages without changing workflow JSON types."""

from __future__ import annotations

import json
from typing import Any

from syntara_node_protocol import node_pb2 as pb

MAX_MESSAGE_BYTES = 2_097_152
PORT = 50051
MAX_INVOCATION_ID_LENGTH = 512
CHANNEL_OPTIONS = (
    ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
    ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
    ("grpc.enable_retries", 0),
)


def encode_json(value: Any) -> bytes:  # noqa: ANN401
    """Keep integers and nulls intact instead of converting through protobuf Struct."""
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode()


def decode_object(value: bytes) -> dict[str, Any]:
    """Require an object for each dynamic request field."""
    result = json.loads(value or b"{}")
    if not isinstance(result, dict):
        message = "Expected a JSON object"
        raise TypeError(message)
    return result


def encode_request(invocation: dict[str, Any], identity: str) -> pb.ExecuteRequest:
    """Encode a trusted invocation using the versioned service contract."""
    operation = invocation.get("operation", "execute")
    if operation not in ("execute", "cancel"):
        message = "Unsupported node operation"
        raise ValueError(message)
    return pb.ExecuteRequest(
        invocation_id=identity,
        protocol_version=invocation.get("version", 1),
        operation=pb.CANCEL_EXTERNAL if operation == "cancel" else pb.EXECUTE,
        inputs_json=encode_json(invocation.get("inputs", {})),
        credentials_json=encode_json(invocation.get("credentials", {})),
        workflow_context_json=encode_json(invocation.get("workflow_context", {})),
        settings_json=encode_json(invocation.get("settings", {})),
        timeout_seconds=invocation.get("timeout_seconds", 300),
        max_output_bytes=invocation.get("max_output_bytes", 1_048_576),
    )


def decode_request(request: pb.ExecuteRequest) -> dict[str, Any]:
    """Reject unsupported versions and operations before running any node code."""
    if (
        request.protocol_version != 1
        or not request.invocation_id
        or len(request.invocation_id) > MAX_INVOCATION_ID_LENGTH
        or request.operation not in (pb.EXECUTE, pb.CANCEL_EXTERNAL)
        or request.ByteSize() > MAX_MESSAGE_BYTES
    ):
        message = "Invalid invocation envelope"
        raise ValueError(message)
    return {
        "version": 1,
        "operation": "cancel" if request.operation == pb.CANCEL_EXTERNAL else "execute",
        "inputs": decode_object(request.inputs_json),
        "credentials": decode_object(request.credentials_json),
        "workflow_context": decode_object(request.workflow_context_json),
        "settings": decode_object(request.settings_json),
        "timeout_seconds": request.timeout_seconds,
        "max_output_bytes": request.max_output_bytes,
    }


def encode_event(frame: dict[str, Any], identity: str) -> pb.ExecutionEvent:
    """Encode sanitized progress or the SDK's terminal result."""
    if frame["kind"] == "progress":
        return pb.ExecutionEvent(
            invocation_id=identity,
            progress=pb.Progress(event=frame["event"], data_json=encode_json(frame.get("data", {}))),
        )
    result, error = frame["result"], frame.get("error") or {}
    return pb.ExecutionEvent(
        invocation_id=identity,
        result=pb.Result(
            output_json=encode_json(result.get("Result")),
            status_code=result["StatusCode"],
            status_message=result.get("StatusMessage") or "",
            error_message=result.get("ErrorMessage") or "",
            error_type=error.get("type") or "",
            retryable=error.get("retryable", False),
        ),
    )


def decode_event(event: pb.ExecutionEvent, identity: str) -> dict[str, Any]:
    """Recover the internal SDK envelope and verify correlation."""
    if event.invocation_id != identity:
        message = "Node event has the wrong invocation ID"
        raise ValueError(message)
    if event.WhichOneof("event") == "progress":
        return {
            "version": 1,
            "kind": "progress",
            "event": event.progress.event,
            "data": decode_object(event.progress.data_json),
        }
    if event.WhichOneof("event") != "result":
        message = "Missing node event"
        raise ValueError(message)
    result = event.result
    return {
        "version": 1,
        "kind": "result",
        "result": {
            "Result": json.loads(result.output_json),
            "StatusCode": result.status_code,
            "StatusMessage": result.status_message,
            "ErrorMessage": result.error_message,
        },
        "error": {"type": result.error_type, "retryable": result.retryable} if result.error_type else None,
    }
