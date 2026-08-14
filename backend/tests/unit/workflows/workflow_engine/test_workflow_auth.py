"""Tests for Temporal workflow authorization utilities and interceptors."""

import hashlib
import hmac as hmac_mod
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.api.common.v1 import Payload
from temporalio.converter import DataConverter
from temporalio.exceptions import ApplicationError
from temporalio.worker import WorkflowInboundInterceptor

# Deterministic 32-byte test key (not derived from HKDF in tests)
_TEST_KEY = os.urandom(32)


_DEFAULT_ARGS: list[Any] = [{"schema_version": "2.0.0"}, "exec-1", "trigger_manual"]


def _fingerprint(args: Sequence[Any]) -> str:
    from syntara.workflows.workflow_engine.workflow_auth import _fingerprint_args

    return _fingerprint_args(args)


def _sign(
    workflow_id: str,
    workflow_type: str = "orchestrator_workflow",
    args: Sequence[Any] = _DEFAULT_ARGS,
) -> bytes:
    message = f"{workflow_id}\n{workflow_type}\n{_fingerprint(args)}".encode()
    return hmac_mod.new(_TEST_KEY, message, hashlib.sha256).digest()


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
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow

            args = [{"key": "value"}, "exec-1"]
            token = sign_workflow("wf-1", "orchestrator_workflow", args)
            assert verify_workflow("wf-1", "orchestrator_workflow", args, token)

    def test_wrong_workflow_id_rejected(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow

            args = ["a", "b"]
            token = sign_workflow("workflow-a", "orchestrator_workflow", args)
            assert not verify_workflow("workflow-b", "orchestrator_workflow", args, token)

    def test_wrong_workflow_type_rejected(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow

            args = ["a", "b"]
            token = sign_workflow("workflow-a", "orchestrator_workflow", args)
            assert not verify_workflow("workflow-a", "malicious_workflow", args, token)

    def test_wrong_args_rejected(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow

            token = sign_workflow("wf-1", "orchestrator_workflow", ["legit-wf", "trigger"])
            assert not verify_workflow("wf-1", "orchestrator_workflow", ["evil-wf", "trigger"], token)

    def test_sign_verify_after_temporal_round_trip(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow

            raw_args: list[Any] = [
                datetime(2024, 1, 1, tzinfo=UTC),
                {"nested": "value"},
                "trigger_manual",
            ]
            token = sign_workflow("wf-1", "orchestrator_workflow", raw_args)
            converter = DataConverter.default.payload_converter
            decoded_args = converter.from_payloads(converter.to_payloads(raw_args))
            assert verify_workflow("wf-1", "orchestrator_workflow", decoded_args, token)

    def test_fingerprint_args_distinct_for_concatenation_collisions(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import _fingerprint_args

            assert _fingerprint_args([12, 3]) != _fingerprint_args([1, 23])
            assert _fingerprint_args([]) != _fingerprint_args([None])
            assert _fingerprint_args([None]) != _fingerprint_args([None, None])

    def test_schedule_launcher_timestamp_suffix_accepted(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow

            wf_id = "4297d494-0336-474e-9165-49411e2facc6"
            trigger_id = "sched_trigger"
            base_id = f"sched-exec-{wf_id}-{trigger_id}"
            runtime_id = f"{base_id}-2026-08-13T16:47:31Z"
            args = [wf_id, trigger_id]
            token = sign_workflow(base_id, "scheduled_workflow_launcher", args)
            assert verify_workflow(runtime_id, "scheduled_workflow_launcher", args, token)

    def test_schedule_launcher_invalid_suffix_rejected(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow

            wf_id = "4297d494-0336-474e-9165-49411e2facc6"
            trigger_id = "sched_trigger"
            base_id = f"sched-exec-{wf_id}-{trigger_id}"
            args = [wf_id, trigger_id]
            token = sign_workflow(base_id, "scheduled_workflow_launcher", args)
            assert not verify_workflow(f"{base_id}-evil", "scheduled_workflow_launcher", args, token)

    def test_invalid_token_rejected(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import verify_workflow

            assert not verify_workflow("wf-1", "orchestrator_workflow", [], b"not-a-valid-hmac")

    def test_build_auth_header_returns_payload(self) -> None:
        with patch(
            "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
            return_value=_TEST_KEY,
        ):
            from syntara.workflows.workflow_engine.workflow_auth import HEADER_NAME, build_auth_header

            headers = build_auth_header("my-workflow-id", "orchestrator_workflow", ["a", "b"])
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
        test_args: list[Any] = ["wf-def", "exec-1", "trigger"]
        token = _sign(info.workflow_id, info.workflow_type, test_args)
        input_data = _FakeExecuteWorkflowInput(
            args=test_args,
            headers={"x-workflow-auth": Payload(data=token)},
        )

        with (
            patch("syntara.workflows.workflow_engine.interceptors.auth_interceptor.workflow") as mock_wf,
            patch(
                "syntara.workflows.workflow_engine.interceptors.auth_interceptor.verify_workflow",
                side_effect=lambda wid, wtype, args, tok: hmac_mod.compare_digest(_sign(wid, wtype, args), tok),
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
                "syntara.workflows.workflow_engine.interceptors.auth_interceptor.verify_workflow",
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
    workflow: str = "orchestrator_workflow"
    args: list[Any] = field(default_factory=lambda: list(_DEFAULT_ARGS))
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
            "syntara.workflows.workflow_engine.client_interceptor.sign_workflow",
            return_value=_sign(input_data.id, input_data.workflow),
        ):
            await outbound.start_workflow(input_data)  # type: ignore[arg-type]

        assert "x-workflow-auth" in input_data.headers
        assert isinstance(input_data.headers["x-workflow-auth"], Payload)
