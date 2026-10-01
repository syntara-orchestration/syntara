# ruff: noqa: INP001, T201
"""Exercise all five images as arbitrary UIDs against a disposable local HTTP service."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from http import HTTPStatus

ENGINE = os.environ.get("CONTAINER_ENGINE", "podman")
REGISTRY = os.environ.get("REGISTRY", "localhost")
TAG = os.environ.get("TAG", "migration-test")
ID = "d278f948-d329-438e-b0fd-2d993a7d9c0f"
SERVER = """
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, data):
        payload=json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def do_GET(self): self.reply({"status":"successful", "artifacts":{"answer":42}, "hello":"world"})
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length",0)))
        self.reply({"id":"d278f948-d329-438e-b0fd-2d993a7d9c0f"} if self.path.endswith("/invocations") else {"id":42})
HTTPServer(("0.0.0.0",8080),Handler).serve_forever()
"""


def command(*args: str, data: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a container command without a shell or inherited invocation secrets."""
    return subprocess.run([ENGINE, *args], input=data, text=True, capture_output=True, check=check, timeout=90)  # noqa: S603


def main() -> None:
    """Create test-only resources, assert node results, then remove our resources."""
    suffix = uuid.uuid4().hex[:10]
    network, server = f"syntara-node-smoke-{suffix}", f"syntara-node-fixture-{suffix}"
    command("network", "create", network)
    try:
        command(
            "run",
            "--rm",
            "-d",
            "--name",
            server,
            "--network",
            network,
            "--network-alias",
            "mock-service",
            "--entrypoint",
            "python",
            f"{REGISTRY}/syntara-node-script:{TAG}",
            "-c",
            SERVER,
        )
        for _ in range(30):
            probe = command(
                "exec",
                server,
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://localhost:8080')",
                check=False,
            )
            if probe.returncode == 0:
                break
            time.sleep(0.2)
        else:
            message = "Mock HTTP service did not start"
            raise RuntimeError(message)
        base = "http://mock-service:8080"
        cases = {
            "http-request": {
                "inputs": {"method": "GET", "url": base},
                "settings": {"workflow_http_request_allowed_hosts": ["mock-service"]},
            },
            "script": {"inputs": {"language": "python", "code": "print('{\"answer\":42}')"}},
            "agent": {
                "inputs": {"prompt": "hello"},
                "workflow_context": {
                    "project_id": ID,
                    "created_by_user_id": ID,
                    "agent_base_url": base,
                    "agent_tls_enabled": False,
                },
            },
            "aap-job": {"inputs": {"job_template_id": 1}},
            "aap-workflow": {"inputs": {"workflow_job_template_id": 1}},
        }
        for name, invocation in cases.items():
            if name.startswith("aap-"):
                invocation.update(
                    credentials={"resolved": {"extra_vars": {"aap_oauth_token": "test-token"}}},
                    workflow_context={"integration": {"base_url": base, "verify_ssl": True}},
                )
            node_container = f"syntara-node-{name}-{suffix}"
            command(
                "run",
                "--rm",
                "-d",
                "--name",
                node_container,
                "--network",
                network,
                "--read-only",
                "--tmpfs",
                "/tmp",  # noqa: S108 - container-local tmpfs
                "--user",
                "1001230000:0",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                f"{REGISTRY}/syntara-node-{name}:{TAG}",
            )
            try:
                result = command(
                    "run",
                    "--rm",
                    "-i",
                    "--network",
                    f"container:{node_container}",
                    "--entrypoint",
                    "python",
                    f"{REGISTRY}/syntara-node-script:{TAG}",
                    "-m",
                    "syntara_node_protocol",
                    "--address",
                    "127.0.0.1:50051",
                    data=json.dumps({"version": 1, **invocation}),
                    check=False,
                )
            finally:
                command("rm", "-f", node_container, check=False)
            frames = [json.loads(line) for line in result.stdout.splitlines()]
            if result.returncode != 0 or not frames or frames[-1]["result"]["StatusCode"] != 0:
                message = f"{name} failed: {result.stdout}\n{result.stderr}"
                raise RuntimeError(message)
            output = frames[-1]["result"]["Result"]
            if name == "http-request":
                assert output["status_code"] == HTTPStatus.OK  # noqa: S101
                assert output["body"]["hello"] == "world"  # noqa: S101
            elif name == "script":
                assert output["stdout_json"] == {"answer": 42}  # noqa: S101
            elif name == "agent":
                assert output["invocation_id"] == ID  # noqa: S101
            else:
                assert output["artifacts"] == {"answer": 42}  # noqa: S101
            print(f"PASS {name}: gRPC, arbitrary UID, read-only filesystem, SDK result", flush=True)
    finally:
        command("rm", "-f", server, check=False)
        command("network", "rm", network, check=False)


if __name__ == "__main__":
    main()
