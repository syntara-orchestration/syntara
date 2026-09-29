"""One gRPC invocation, streamed events and cooperative cancellation."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

import grpc

from syntara_node_protocol import node_pb2 as pb
from syntara_node_protocol import node_pb2_grpc as rpc
from syntara_node_protocol.codec import MAX_MESSAGE_BYTES, decode_event, encode_request

if TYPE_CHECKING:
    from collections.abc import Callable


class NodeRpcError(Exception):
    """A safe transport diagnostic with an explicit retry classification."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        """Record whether the failure occurred before Execute could be submitted."""
        super().__init__(message)
        self.retryable = retryable


def cancel_rpc(call: grpc.Call) -> None:
    """Cancel a streaming call (grpc-stubs omits this return annotation)."""
    call.cancel()  # type: ignore[no-untyped-call]


def invoke(  # noqa: C901, PLR0912, PLR0915
    channel: grpc.Channel,
    invocation: dict[str, Any],
    *,
    identity: str,
    progress: Callable[[dict[str, Any]], None],
    cancelled: threading.Event,
    startup: float = 120,
    grace: int = 30,
) -> dict[str, Any]:
    """Wait for health, submit Execute once, and require exactly one final result."""
    request = encode_request(invocation, identity)
    if request.ByteSize() > MAX_MESSAGE_BYTES:
        message = "Node invocation exceeds transport limit"
        raise NodeRpcError(message)
    stub = rpc.NodeServiceStub(channel)
    deadline = time.monotonic() + startup
    while True:
        if cancelled.is_set():
            message = "Node execution cancelled before submission"
            raise NodeRpcError(message)
        try:
            health = stub.Health(pb.HealthRequest(), timeout=min(1, max(0.1, deadline - time.monotonic())))
            if not health.ready or health.protocol_version != 1:
                message = "Node server is unavailable or incompatible"
                raise NodeRpcError(message)
            break
        except grpc.RpcError:
            if time.monotonic() >= deadline:
                message = "Node gRPC server did not become ready"
                raise NodeRpcError(message, retryable=True) from None
            cancelled.wait(0.1)
    # Even a transport failure before the first response may have executed work.
    if cancelled.is_set():
        message = "Node execution cancelled before submission"
        raise NodeRpcError(message)
    call = stub.Execute(request, timeout=request.timeout_seconds + grace)
    stopped = threading.Event()

    def monitor() -> None:
        while not stopped.wait(0.1):
            if cancelled.is_set():
                try:
                    response = stub.Cancel(pb.CancelRequest(invocation_id=identity), timeout=5)
                    if not response.accepted:
                        cancel_rpc(call)
                        return
                except grpc.RpcError:
                    cancel_rpc(call)
                    return
                if not stopped.wait(grace):
                    cancel_rpc(call)
                return

    watcher = threading.Thread(target=monitor, daemon=True, name="node-grpc-cancel")
    watcher.start()
    result: dict[str, Any] | None = None
    try:
        for event in call:
            frame = decode_event(event, identity)
            if result is not None:
                message = "Node returned events after its terminal result"
                raise NodeRpcError(message)
            if frame["kind"] == "progress":
                progress(frame)
            else:
                result = frame
        if result is None:
            message = "Node gRPC stream ended without a result"
            raise NodeRpcError(message)
        return result
    except grpc.RpcError as exc:
        # Never include remote diagnostic text: it may contain credentials.
        message = f"Node gRPC call failed ({exc.code().name})"
        raise NodeRpcError(message) from None
    except (ValueError, KeyError, TypeError):
        message = "Invalid node gRPC result"
        raise NodeRpcError(message) from None
    finally:
        stopped.set()
        cancel_rpc(call)
        watcher.join(timeout=6)
