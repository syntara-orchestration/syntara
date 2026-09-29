"""Real gRPC requests exercise lifecycle, cancellation and wire compatibility."""

import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import grpc
import pytest
from syntara_node_protocol import node_pb2 as pb
from syntara_node_protocol import node_pb2_grpc as rpc
from syntara_node_protocol.client import NodeRpcError, invoke
from syntara_node_protocol.codec import CHANNEL_OPTIONS, MAX_MESSAGE_BYTES, decode_event, encode_request
from syntara_node_runtime.server import create_server
from syntara_node_script import Node


@pytest.fixture
def endpoint():
    server, service, port = create_server(Node(), "127.0.0.1:0")
    server.start()
    with grpc.insecure_channel(f"127.0.0.1:{port}", options=CHANNEL_OPTIONS) as channel:
        yield channel, service
    service.cancelled.set()
    server.stop(2).wait(3)


def invocation(code='print("hello")', language="python", **kwargs):
    return {"inputs": {"language": language, "code": code}, "timeout_seconds": 10, **kwargs}


def execute(channel, data, cancelled=None):
    return invoke(
        channel,
        data,
        identity="test-id",
        progress=lambda _frame: None,
        cancelled=cancelled or threading.Event(),
        startup=2,
        grace=3,
    )


@pytest.mark.parametrize(
    ("language", "code", "expected"), [("python", 'print("hello")', "hello\n"), ("bash", "printf hello", "hello")]
)
def test_execute_over_grpc(endpoint, language, code, expected):
    channel, _service = endpoint
    result = execute(channel, invocation(code, language))
    assert result["result"]["StatusCode"] == 0
    assert result["result"]["Result"]["stdout"] == expected


def test_exact_integer_and_null_output(endpoint):
    channel, _service = endpoint
    result = execute(channel, invocation('print(\'{"id":1152921504606846977,"empty":null}\')'))
    assert result["result"]["Result"]["stdout_json"] == {"id": 1152921504606846977, "empty": None}


def test_failure_preserves_partial_output(endpoint):
    channel, _service = endpoint
    result = execute(channel, invocation("printf partial; exit 7", "bash"))
    assert result["result"]["Result"]["return_code"] == 7
    assert result["result"]["Result"]["stdout"] == "partial"
    assert result["error"]["retryable"] is False


def test_second_execution_rejected(endpoint):
    channel, _service = endpoint
    execute(channel, invocation())
    with pytest.raises(grpc.RpcError) as error:
        list(rpc.NodeServiceStub(channel).Execute(encode_request(invocation(), "second"), timeout=2))
    assert error.value.code() == grpc.StatusCode.ALREADY_EXISTS


def test_cooperative_cancel_returns_terminal_result(endpoint):
    channel, service = endpoint
    cancelled = threading.Event()
    with ThreadPoolExecutor() as executor:
        future = executor.submit(execute, channel, invocation("import time; time.sleep(60)"), cancelled)
        for _ in range(100):
            if service.invocation_id:
                break
            time.sleep(0.01)
        assert service.invocation_id == "test-id"
        cancelled.set()
        result = future.result(timeout=5)
    assert result["error"]["type"] == "CancelledError"


@pytest.mark.parametrize("disconnect", [True, False])
def test_rpc_disconnect_or_deadline_cancels_work(endpoint, disconnect):
    channel, service = endpoint
    call = rpc.NodeServiceStub(channel).Execute(
        encode_request(invocation("import time; time.sleep(60)"), "test"), timeout=0.5
    )
    for _ in range(100):
        if service.invocation_id:
            break
        time.sleep(0.01)
    if disconnect:
        call.cancel()
    with pytest.raises(grpc.RpcError):
        list(call)
    assert service.finished.wait(3)
    assert service.cancelled.is_set()


def test_invalid_request_does_not_leak_credentials(endpoint):
    channel, service = endpoint
    request = encode_request(invocation(), "bad")
    request.credentials_json = b'"do-not-leak"'
    with pytest.raises(grpc.RpcError) as error:
        list(rpc.NodeServiceStub(channel).Execute(request, timeout=2))
    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "do-not-leak" not in error.value.details()
    assert service.invocation_id is None


def test_request_size_limit_before_submission(endpoint):
    channel, service = endpoint
    with pytest.raises(NodeRpcError, match="transport limit"):
        execute(channel, invocation("x" * MAX_MESSAGE_BYTES))
    assert service.invocation_id is None


def test_unencrypted_remote_listener_rejected():
    with pytest.raises(ValueError, match="mutual TLS"):
        create_server(Node(), "0.0.0.0:50051")


def test_event_correlation_required():
    with pytest.raises(ValueError, match="invocation ID"):
        decode_event(pb.ExecutionEvent(invocation_id="wrong"), "expected")


def test_progress_stream_is_redacted():
    class ProgressNode(Node):
        def run(self, inputs, context) -> dict:
            context.emit("heartbeat", {"message": "contains private-token"})
            return super().run(inputs, context)

    server, _service, port = create_server(ProgressNode(), "127.0.0.1:0")
    server.start()
    frames = []
    try:
        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            result = invoke(
                channel,
                invocation(credentials={"resolved": {"extra_vars": {"bearer_token": "private-token"}}}),
                identity="progress",
                progress=frames.append,
                cancelled=threading.Event(),
                startup=2,
            )
        assert frames[0]["event"] == "heartbeat"
        assert frames[0]["data"]["message"] == "contains [REDACTED]"
        assert result["result"]["StatusCode"] == 0
    finally:
        server.stop(2).wait(3)


def test_direct_connection_requires_client_certificate(tmp_path):
    cert, key = tmp_path / "tls.crt", tmp_path / "tls.key"
    openssl = shutil.which("openssl")
    assert openssl is not None
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-days",
            "1",
        ],
        check=True,
        capture_output=True,
    )
    credentials = grpc.ssl_server_credentials(
        [(key.read_bytes(), cert.read_bytes())], root_certificates=cert.read_bytes(), require_client_auth=True
    )
    server, _service, port = create_server(Node(), "0.0.0.0:0", credentials=credentials)
    server.start()
    try:
        unauthenticated = grpc.ssl_channel_credentials(root_certificates=cert.read_bytes())
        with grpc.secure_channel(f"localhost:{port}", unauthenticated) as channel:
            with pytest.raises(grpc.RpcError):
                rpc.NodeServiceStub(channel).Health(pb.HealthRequest(), timeout=0.5)
        authenticated = grpc.ssl_channel_credentials(
            root_certificates=cert.read_bytes(), private_key=key.read_bytes(), certificate_chain=cert.read_bytes()
        )
        with grpc.secure_channel(f"localhost:{port}", authenticated) as channel:
            assert execute(channel, invocation())["result"]["StatusCode"] == 0
    finally:
        server.stop(2).wait(3)
