# ruff: noqa: N802, ANN401 - RPC methods implement the generated protobuf interface
"""A gRPC server accepting one SDK invocation per container."""

from __future__ import annotations

import importlib
import os
import queue
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

import grpc
from syntara_node_protocol import node_pb2 as pb
from syntara_node_protocol import node_pb2_grpc as rpc
from syntara_node_protocol.codec import CHANNEL_OPTIONS, MAX_MESSAGE_BYTES, decode_request, encode_event

from syntara_node_runtime.runtime import Invocation, NodeFailure, execute

if TYPE_CHECKING:
    from collections.abc import Iterator


class NodeService(rpc.NodeServiceServicer):
    """Single admission prevents re-execution after ambiguous client failures."""

    def __init__(self, node: Any) -> None:
        """Initialize invocation ownership and shutdown signals."""
        self.node = node
        self.lock = threading.Lock()
        self.invocation_id: str | None = None
        self.cancelled = threading.Event()
        self.finished = threading.Event()

    def Health(self, _request: pb.HealthRequest, _context: grpc.ServicerContext) -> pb.HealthResponse:
        """Advertise readiness only before the single invocation is admitted."""
        with self.lock:
            return pb.HealthResponse(
                ready=self.invocation_id is None and not self.cancelled.is_set(), protocol_version=1
            )

    def Cancel(self, request: pb.CancelRequest, _context: grpc.ServicerContext) -> pb.CancelResponse:
        """Request cleanup while allowing Execute to return partial output."""
        with self.lock:
            accepted = bool(
                request.invocation_id and request.invocation_id == self.invocation_id and not self.finished.is_set()
            )
            if accepted:
                self.cancelled.set()
        return pb.CancelResponse(accepted=accepted)

    def Execute(self, request: pb.ExecuteRequest, context: grpc.ServicerContext) -> Iterator[pb.ExecutionEvent]:  # noqa: C901, PLR0915
        """Stream sanitized progress followed by exactly one terminal result."""
        try:
            invocation = Invocation.model_validate(decode_request(request))
        except (ValueError, TypeError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid node invocation")
            return
        with self.lock:
            if self.invocation_id is not None or self.cancelled.is_set():
                context.abort(grpc.StatusCode.ALREADY_EXISTS, "This pod already accepted an invocation")
            self.invocation_id = request.invocation_id
        context.add_callback(self.cancelled.set)
        events: queue.Queue[pb.ExecutionEvent | None] = queue.Queue(maxsize=128)
        timed_out = threading.Event()

        def timeout() -> None:
            timed_out.set()
            self.cancelled.set()

        def send(frame: dict[str, Any]) -> None:
            if timed_out.is_set() and (frame.get("error") or {}).get("type") == "CancelledError":
                frame["error"]["type"] = "TimeoutError"
                frame["result"]["StatusMessage"] = "Node execution timed out"
            event = encode_event(frame, request.invocation_id)
            if event.ByteSize() > MAX_MESSAGE_BYTES:
                self.cancelled.set()
                if frame["kind"] == "progress":
                    message = "Progress message exceeds the transport limit"
                    raise NodeFailure(message, type="OutputLimitError")
                event = pb.ExecutionEvent(
                    invocation_id=request.invocation_id,
                    result=pb.Result(
                        output_json=b"null",
                        status_code=1,
                        status_message="Output limit exceeded",
                        error_type="OutputLimitError",
                    ),
                )
            while context.is_active():
                try:
                    events.put(event, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def run() -> None:
            try:
                execute(self.node, invocation, send, cancellation=self.cancelled)
            except Exception:  # noqa: BLE001 - suppress raw worker-thread exceptions at the RPC boundary
                send(
                    {
                        "kind": "result",
                        "result": {"Result": None, "StatusCode": 1, "StatusMessage": "Node execution failed"},
                        "error": {"type": "NodeExecutionError", "retryable": False},
                    }
                )
            finally:
                while context.is_active():
                    try:
                        events.put(None, timeout=0.1)
                        break
                    except queue.Full:
                        continue

        # Node-specific timeout handlers get the first opportunity to preserve output.
        timer = threading.Timer(invocation.timeout_seconds + 0.1, timeout)
        worker = threading.Thread(target=run, daemon=True, name="sdk-node-execution")
        timer.start()
        worker.start()
        try:
            while context.is_active():
                try:
                    event = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if event is None:
                    return
                yield event
        finally:
            self.cancelled.set()
            timer.cancel()
            worker.join(timeout=30)
            self.finished.set()


def create_server(
    node: Any, address: str = "127.0.0.1:50051", *, credentials: grpc.ServerCredentials | None = None
) -> tuple[grpc.Server, NodeService, int]:
    """Create a server; remote listeners require mutual TLS."""
    if credentials is None and address.rsplit(":", 1)[0] not in {"127.0.0.1", "localhost", "[::1]"}:
        message = "A non-loopback gRPC listener requires mutual TLS"
        raise ValueError(message)
    service = NodeService(node)
    server = grpc.server(ThreadPoolExecutor(max_workers=4), options=CHANNEL_OPTIONS)
    rpc.add_NodeServiceServicer_to_server(service, server)
    port = server.add_secure_port(address, credentials) if credentials else server.add_insecure_port(address)
    if not port:
        message = "Cannot bind the node gRPC listener"
        raise RuntimeError(message)
    return server, service, port


def main() -> None:
    """Serve gRPC until the invocation finishes or the pod is terminated."""
    module = importlib.import_module(os.environ["SYNTARA_NODE_MODULE"])
    cert, key, ca = (os.getenv(f"SYNTARA_NODE_GRPC_TLS_{name}") for name in ("CERT", "KEY", "CA"))
    credentials = None
    if any((cert, key, ca)):
        if cert is None or key is None or ca is None:
            message = "gRPC TLS requires certificate, key and client CA paths"
            raise ValueError(message)
        credentials = grpc.ssl_server_credentials(
            [(Path(key).read_bytes(), Path(cert).read_bytes())],
            root_certificates=Path(ca).read_bytes(),
            require_client_auth=True,
        )
    server, service, _port = create_server(
        module.Node(), os.getenv("SYNTARA_NODE_GRPC_ADDRESS", "127.0.0.1:50051"), credentials=credentials
    )
    stopping = threading.Event()

    def terminate(_signum: int, _frame: Any) -> None:
        service.cancelled.set()
        stopping.set()

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    server.start()
    while not service.finished.wait(0.1):
        if stopping.is_set():
            break
    server.stop(grace=30).wait(timeout=35)


if __name__ == "__main__":
    main()
