"""Tests for Temporal workflow authorization utilities and interceptors."""

import hashlib
import hmac as hmac_mod
import os
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.api.common.v1 import Payload
from temporalio.exceptions import ApplicationError
from temporalio.worker import WorkflowInboundInterceptor

# Deterministic 32-byte test key (not derived from HKDF in tests)
_TEST_KEY = os.urandom(32)


def _sign(workflow_id: str) -> bytes:
    return hmac_mod.new(_TEST_KEY, workflow_id.encode(), hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# workflow_auth module tests
# ---------------------------------------------------------------------------


class TestWorkflowAuth:
    """Tests for HMAC sign/verify/header utilities."""

    def test_sign_verify_roundtrip(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow_id, verify_workflow_id

            workflow_id = "test-workflow-abc123"
            token = sign_workflow_id(workflow_id)
            assert verify_workflow_id(workflow_id, token)

    def test_wrong_workflow_id_rejected(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow_id, verify_workflow_id

            token = sign_workflow_id("workflow-a")
            assert not verify_workflow_id("workflow-b", token)

    def test_invalid_token_rejected(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import verify_workflow_id

            assert not verify_workflow_id("workflow-a", b"not-a-valid-hmac")

    def test_build_auth_header_returns_payload(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import HEADER_NAME, build_auth_header

            headers = build_auth_header("my-workflow-id")
            assert HEADER_NAME in headers
            assert isinstance(headers[HEADER_NAME], Payload)
            assert len(headers[HEADER_NAME].data) == 32  # SHA-256 digest


# ---------------------------------------------------------------------------
# Worker-side auth interceptor tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeWorkflowInfo:
    workflow_id: str = "test-wf-123"
    workflow_type: str = "orchestrator_workflow"
    parent: Any = None


@dataclass
class _FakeExecuteWorkflowInput:
    args: list[Any] = field(default_factory=list)
    headers: dict[str, Payload] = field(default_factory=dict)


class TestWorkflowAuthInboundInterceptor:
    """Tests for _WorkflowAuthInboundInterceptor."""

    @staticmethod
    def _make_interceptor() -> WorkflowInboundInterceptor:
        from syntara.workflows.workflow_engine.interceptors.auth_interceptor import _WorkflowAuthInboundInterceptor

        next_interceptor = MagicMock()
        next_interceptor.execute_workflow = MagicMock()
        return _WorkflowAuthInboundInterceptor(next_interceptor)

    @pytest.mark.asyncio
    async def test_valid_hmac_allows_execution(self) -> None:
        interceptor = self._make_interceptor()
        info = _FakeWorkflowInfo()
        token = _sign(info.workflow_id)
        input_data = _FakeExecuteWorkflowInput(
            headers={"x-workflow-auth": Payload(data=token)},
        )

        with (
            patch("syntara.workflows.workflow_engine.interceptors.auth_interceptor.workflow") as mock_wf,
            patch(
                "syntara.workflows.workflow_engine.interceptors.auth_interceptor.verify_workflow_id",
                side_effect=lambda wid, tok: hmac_mod.compare_digest(_sign(wid), tok),
            ),
        ):
            mock_wf.info.return_value = info
            interceptor.next = MagicMock()
            interceptor.next.execute_workflow = AsyncMock(return_value="result")

            result = await interceptor.execute_workflow(input_data)  # type: ignore[arg-type]
            assert result == "result"

    @pytest.mark.asyncio
    async def test_missing_header_rejects(self) -> None:
        interceptor = self._make_interceptor()
        info = _FakeWorkflowInfo()
        input_data = _FakeExecuteWorkflowInput(headers={})

        with patch("syntara.workflows.workflow_engine.interceptors.auth_interceptor.workflow") as mock_wf:
            mock_wf.info.return_value = info

            with pytest.raises(ApplicationError, match="Unauthorized"):
                await interceptor.execute_workflow(input_data)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_invalid_hmac_rejects(self) -> None:
        interceptor = self._make_interceptor()
        info = _FakeWorkflowInfo()
        input_data = _FakeExecuteWorkflowInput(
            headers={"x-workflow-auth": Payload(data=b"bad-token")},
        )

        with (
            patch("syntara.workflows.workflow_engine.interceptors.auth_interceptor.workflow") as mock_wf,
            patch(
                "syntara.workflows.workflow_engine.interceptors.auth_interceptor.verify_workflow_id",
                return_value=False,
            ),
        ):
            mock_wf.info.return_value = info

            with pytest.raises(ApplicationError, match="Unauthorized"):
                await interceptor.execute_workflow(input_data)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_child_workflow_allowed_without_header(self) -> None:
        interceptor = self._make_interceptor()
        info = _FakeWorkflowInfo(parent=MagicMock())
        input_data = _FakeExecuteWorkflowInput(headers={})

        with patch("syntara.workflows.workflow_engine.interceptors.auth_interceptor.workflow") as mock_wf:
            mock_wf.info.return_value = info
            interceptor.next = MagicMock()
            interceptor.next.execute_workflow = AsyncMock(return_value="child-result")

            result = await interceptor.execute_workflow(input_data)  # type: ignore[arg-type]
            assert result == "child-result"


# ---------------------------------------------------------------------------
# Client-side interceptor tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeStartWorkflowInput:
    id: str = "test-wf-456"
    headers: dict[str, Payload] = field(default_factory=dict)


class TestWorkflowAuthClientInterceptor:
    """Tests for WorkflowAuthClientInterceptor."""

    @pytest.mark.asyncio
    async def test_injects_auth_header(self) -> None:
        from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor

        next_outbound = MagicMock()
        next_outbound.start_workflow = AsyncMock(return_value="handle")

        interceptor = WorkflowAuthClientInterceptor()
        outbound = interceptor.intercept_client(next_outbound)

        input_data = _FakeStartWorkflowInput()
        with patch(
            "syntara.workflows.workflow_engine.client_interceptor.sign_workflow_id",
            return_value=_sign(input_data.id),
        ):
            await outbound.start_workflow(input_data)  # type: ignore[arg-type]

        assert "x-workflow-auth" in input_data.headers
        assert isinstance(input_data.headers["x-workflow-auth"], Payload)
