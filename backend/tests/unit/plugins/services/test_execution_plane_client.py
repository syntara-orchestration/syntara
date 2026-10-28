"""Tests for the Execution Plane dispatch client and plugin_action wiring."""

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from syntara.plugins.services.execution_plane_client import (
    ExecutionPlaneClient,
    ExecutionPlaneError,
)
from syntara.workflows.workflow_engine.activities.plugin_action_activity import (
    _dispatch_to_execution_plane,
)


def _ec_private_pem() -> bytes:
    """Serialize a fresh ES256 key so service tokens can really be minted."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())


class _StubSettings:
    """Minimal settings surface used by ExecutionPlaneClient."""

    jwt_private_key_path: str | None = None
    jwt_issuer = "https://localhost:8000"
    execution_plane_jwt_issuer = "http://localhost:8000"
    execution_plane_api_url: str | None = "https://api:8443"
    execution_plane_api_ca_path: str | None = None
    execution_plane_client_id = "syntara-orchestration"
    execution_plane_jwt_audience = "execution-plane"
    execution_plane_request_timeout_seconds = 5.0
    execution_plane_poll_interval_seconds = 0.0


@pytest.fixture
def stub_settings(tmp_path: Path) -> _StubSettings:
    """Provide settings whose JWT key is a real ES256 key so tokens mint."""
    key = tmp_path / "jwt-primary.pem"
    key.write_bytes(_ec_private_pem())
    settings = _StubSettings()
    settings.jwt_private_key_path = str(key)
    return settings


def _client_with_transport(transport: httpx.MockTransport, stub_settings: _StubSettings) -> ExecutionPlaneClient:
    """Build a client whose HTTP layer is a MockTransport."""
    with patch("syntara.plugins.services.execution_plane_client.get_settings", return_value=stub_settings):
        client = ExecutionPlaneClient()

    def _transport_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=5.0,
            verify=False,  # noqa: S501 - test transport, no real TLS
            transport=transport,
        )

    client._http_client = _transport_factory  # type: ignore[method-assign] - test seam
    return client


class TestBuildWorkExecuteMessage:
    """The command envelope must match the execution_plane_client wire format."""

    def test_envelope_shape(self, stub_settings: _StubSettings) -> None:
        with patch("syntara.plugins.services.execution_plane_client.get_settings", return_value=stub_settings):
            client = ExecutionPlaneClient()
        message = client._build_work_execute_message(
            work_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            image="localhost:5000/img@sha256:abc",
            step_revision_id="syntara.script-step.python",
            workflow_run_id="wf-1",
            inputs={"code": "print(1 + 1)"},
            timeout_seconds=60,
            output_config={"stdout": "stdout"},
        )
        assert message["message_type"] == "command.submit"
        assert message["source_id"] == "syntara-orchestration"
        assert message["scope"] == {"client_id": "syntara-orchestration"}
        command = message["command"]
        assert command["command_type"] == "work.execute"
        assert command["command_revision"] == 1
        payload = command["payload"]
        assert payload["image"] == "localhost:5000/img@sha256:abc"
        assert payload["workload_type"] == "container"
        invocation = payload["invocation"]
        assert invocation["step_revision_id"] == "syntara.script-step.python"
        assert invocation["workflow_run_id"] == "wf-1"
        assert invocation["inputs"] == {"code": "print(1 + 1)"}
        assert invocation["timeout_seconds"] == 60


class TestSubmitAndWait:
    """Submission and polling against a mocked Execution Plane API."""

    @pytest.mark.asyncio
    async def test_completed_work_item_returned(self, stub_settings: _StubSettings) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/v1/commands":
                return httpx.Response(202, json={"status": "accepted"})
            assert request.url.path.startswith("/v1/work-items/")
            return httpx.Response(
                200,
                json={
                    "id": "22222222-2222-2222-2222-222222222222",
                    "status": "completed",
                    "result": {"output": {"stdout": "2\n", "return_code": 0}},
                },
            )

        client = _client_with_transport(httpx.MockTransport(handler), stub_settings)
        item = await client.submit_and_wait(
            image="localhost:5000/img@sha256:abc",
            step_revision_id="s.python",
            workflow_run_id="wf-1",
            inputs={"code": "print(1 + 1)"},
            timeout_seconds=5,
        )
        assert item["status"] == "completed"
        assert item["result"]["output"]["stdout"] == "2\n"
        assert requests[0].method == "POST"
        assert requests[0].headers["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_submit_rejection_raises(self, stub_settings: _StubSettings) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"detail": "forbidden"})

        client = _client_with_transport(httpx.MockTransport(handler), stub_settings)
        with pytest.raises(ExecutionPlaneError, match="submit failed"):
            await client.submit_and_wait(
                image="img",
                step_revision_id="s",
                workflow_run_id="wf",
                inputs={},
                timeout_seconds=5,
            )

    @pytest.mark.asyncio
    async def test_missing_api_url_raises(self, stub_settings: _StubSettings) -> None:
        stub_settings.execution_plane_api_url = None
        with patch("syntara.plugins.services.execution_plane_client.get_settings", return_value=stub_settings):
            client = ExecutionPlaneClient()
        with pytest.raises(ExecutionPlaneError, match="APP_EXECUTION_PLANE_API_URL"):
            await client.submit_and_wait(
                image="img",
                step_revision_id="s",
                workflow_run_id="wf",
                inputs={},
                timeout_seconds=5,
            )


class TestDispatchToExecutionPlane:
    """Mapping of terminal work items into the activity's output envelope."""

    @pytest.mark.asyncio
    async def test_completed_maps_output(self) -> None:
        class _StubClient:
            async def submit_and_wait(self, **kwargs: object) -> dict[str, Any]:
                assert kwargs["step_revision_id"] == "syntara.script-step.python"
                assert kwargs["inputs"] == {"code": "print(1 + 1)"}
                return {
                    "id": "wi-1",
                    "status": "completed",
                    "result": {"output": {"stdout": "2\n", "stderr": "", "return_code": 0}},
                }

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.plugin_action_activity.ExecutionPlaneClient",
                return_value=_StubClient(),
            ),
        ):
            envelope = await _dispatch_to_execution_plane(
                "wf-run-1",
                {
                    "identity": "syntara.script-step.python",
                    "workload_image": "localhost:5000/img@sha256:abc",
                },
                {"code": "print(1 + 1)"},
                None,
            )
        output = envelope["output"]
        assert output["status"] == "completed"
        assert output["executed_via"] == "execution-plane"
        assert output["stdout"] == "2\n"
        assert output["return_code"] == 0

    @pytest.mark.asyncio
    async def test_failed_work_item_maps_error(self) -> None:
        class _StubClient:
            async def submit_and_wait(self, **kwargs: object) -> dict[str, Any]:
                return {
                    "id": "wi-2",
                    "status": "failed",
                    "result": {"error": " INVALID_INPUT", "status_message": "boom"},
                }

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.plugin_action_activity.ExecutionPlaneClient",
                return_value=_StubClient(),
            ),
        ):
            envelope = await _dispatch_to_execution_plane(
                "wf-run-1",
                {"identity": "a", "workload_image": "img"},
                {},
                None,
            )
        assert envelope["output"]["status"] == "failed"
        assert "INVALID_INPUT" in envelope["output"]["error"]

    @pytest.mark.asyncio
    async def test_missing_workload_image_fails_fast(self) -> None:
        envelope = await _dispatch_to_execution_plane(
            "wf-run-1",
            {"identity": "a"},
            {},
            None,
        )
        assert envelope["output"]["status"] == "failed"
        assert "workload_image" in envelope["output"]["error"]
