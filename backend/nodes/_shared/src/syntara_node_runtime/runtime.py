# ruff: noqa: ANN401, A002
"""SDK execution support shared by the gRPC node servers."""

from __future__ import annotations

import asyncio
import contextvars
import json
import signal
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal, cast

import structlog
from pydantic import Field, SecretStr, ValidationError
from sqlmodel import SQLModel
from syntara_sdk import ExecutionContext, StandardOutputWrapper

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

MAX_FRAME_BYTES = 2_097_152
constants = SimpleNamespace(ENGINE_TIMEOUT_SECONDS_KEY="_engine_timeout_seconds")


class NodeSettings(SQLModel):
    """Non-secret limits supplied by the trusted dispatcher."""

    workflow_http_request_allowed_hosts: list[str] = Field(default_factory=list)
    aap_poll_interval_seconds: float = Field(default=5, gt=0)
    aap_token: SecretStr | None = None
    aap_username: str | None = None
    aap_password: SecretStr | None = None
    script_cleanup_terminate_timeout: float = 1
    script_cleanup_kill_timeout: float = 0.5
    temporal_payload_max_bytes: int = int(MAX_FRAME_BYTES * 0.9)
    max_env_var_length: int = 32768


class Invocation(SQLModel):
    """Transport v1: credentials are separate from user-controlled inputs."""

    model_config = {"extra": "forbid"}
    version: Literal[1] = 1
    operation: Literal["execute", "cancel"] = "execute"
    inputs: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)
    workflow_context: dict[str, Any] = Field(default_factory=dict)
    settings: NodeSettings = Field(default_factory=NodeSettings)
    timeout_seconds: int = Field(default=300, ge=1)
    max_output_bytes: int = Field(default=1048576, ge=1, le=MAX_FRAME_BYTES)


class NodeFailure(Exception):  # noqa: N818 - matches the portable failure contract
    """Portable failure with legacy classification and partial output."""

    def __init__(
        self, message: str, *details: Any, type: str = "NodeExecutionError", non_retryable: bool = True
    ) -> None:
        """Initialize the node contract and execution state."""
        super().__init__(message)
        self.error_type = type
        self.non_retryable = non_retryable
        self.details = details


def secret_values(value: Any) -> set[str]:
    """Collect credential values for replacement, including short secrets."""
    if isinstance(value, dict):
        return set().union(*(secret_values(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(secret_values(v) for v in value)) if value else set()
    return {value} if isinstance(value, str) and value else set()


def scrub(value: Any, secrets: set[str]) -> Any:
    """Redact nested credential keys and known values without logging inputs."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if any(s in k.lower() for s in ("password", "authorization", "token", "api_key", "secret"))
            else scrub(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
    return value


class RuntimeContext(ExecutionContext):
    """SDK context with progress and cooperative cancellation."""

    def __init__(self, invocation: Invocation, writer: Callable[[dict[str, Any]], None]) -> None:
        """Initialize the node contract and execution state."""
        ctx = invocation.workflow_context
        super().__init__(execution_id=ctx.get("execution_id"), workflow_id=ctx.get("workflow_id"))
        self.invocation = invocation
        self.writer = writer
        self.cancelled = threading.Event()
        resolved = invocation.credentials.get("resolved", {})
        self.secrets = secret_values(resolved.get("_secret_values", []))
        self.secrets |= secret_values({k: v for k, v in resolved.get("extra_vars", {}).items() if k != "auth_type"})
        self.secrets |= secret_values(resolved.get("env", {})) | secret_values(resolved.get("file", {}))
        self.partial: dict[str, Any] = {}

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Write a sanitized progress frame."""
        self.writer(scrub({"version": 1, "kind": "progress", "event": event, "data": data}, self.secrets))

    def input_config(self) -> dict[str, Any]:
        """Construct legacy executor inputs from the separated invocation fields."""
        data = {k: v for k, v in self.invocation.inputs.items() if not k.startswith("_")}
        data["_resolved_credentials"] = self.invocation.credentials.get("resolved")
        data["_resolved_integration"] = self.invocation.workflow_context.get("integration")
        data["_engine_timeout_seconds"] = self.invocation.timeout_seconds
        data["_engine_max_output_bytes"] = self.invocation.max_output_bytes
        return data


_current: contextvars.ContextVar[RuntimeContext] = contextvars.ContextVar("node_context")


def get_settings() -> NodeSettings:
    """Read limits from the current invocation."""
    return _current.get().invocation.settings


def ensure_resolved_credentials_dict(value: Any) -> dict[str, Any]:
    """Require structured resolved credentials."""
    if not isinstance(value, dict):
        message = "Invalid resolved credentials"
        raise NodeFailure(message, type="ConfigError")
    return value


class ExecutionEvents:
    """Transport hooks used by the extracted executor implementations."""

    def heartbeat(self, data: dict[str, Any]) -> None:
        """Emit progress and retain the latest partial output."""
        ctx = _current.get()
        ctx.partial.update(data.get("partial_output", {}))
        ctx.emit("heartbeat", data)

    def is_cancelled(self) -> bool:
        """Report whether termination has been requested."""
        return _current.get().cancelled.is_set()


execution = ExecutionEvents()


def emit_launched(_execution_id: Any, template_id: Any, **kwargs: Any) -> None:
    """Report the launched AAP job to the control plane."""
    _current.get().emit("aap_launched", {"template_id": template_id, **kwargs})


def emit_failed(_execution_id: Any, template_id: Any, **kwargs: Any) -> None:
    """Report AAP failure to the control plane."""
    _current.get().emit("aap_failed", {"template_id": template_id, **kwargs})


def emit_completed(_execution_id: Any, template_id: Any, **kwargs: Any) -> None:
    """Report AAP completion to the control plane."""
    _current.get().emit("aap_completed", {"template_id": template_id, **kwargs})


def is_failure_status(status: str) -> bool:
    """Classify AAP terminal failures."""
    return status in {"failed", "error", "canceled"}


def run_async(call: Callable[[], Coroutine[Any, Any, dict[str, Any]]], context: RuntimeContext) -> dict[str, Any]:
    """Bridge the synchronous SDK run method to cancellation-aware async I/O."""

    async def run() -> dict[str, Any]:
        """Execute validated inputs using the portable runtime."""
        token = _current.set(context)
        task = asyncio.create_task(call())

        async def cancel_watch() -> None:
            """Provide the cancel watch operation."""
            while not context.cancelled.is_set():  # noqa: ASYNC110 - signal handler sets a threading.Event
                await asyncio.sleep(0.1)
            task.cancel()

        watcher = asyncio.create_task(cancel_watch())
        try:
            return await task
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            _current.reset(token)

    return asyncio.run(run())


def execute(
    node: Any,
    invocation: Invocation,
    writer: Callable[[dict[str, Any]], None],
    *,
    cancellation: threading.Event | None = None,
) -> dict[str, Any]:
    """Validate through SDK models, retaining typed failures and partial results."""
    context = RuntimeContext(invocation, writer)
    if cancellation is not None:
        context.cancelled = cancellation
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: context.cancelled.set())
    context.logger.info("Node execution started")
    # Extracted implementations must never print raw inputs or exception tracebacks.
    structlog.configure(processors=[lambda _logger, _method, _event: (_ for _ in ()).throw(structlog.DropEvent)])
    result: Any = None
    failure: dict[str, Any] | None = None
    try:
        inputs = node.input_model.model_validate(invocation.inputs)
        output = node.run(inputs, context)
        result = node.output_model.model_validate(output).model_dump(mode="json")
        wrapper = StandardOutputWrapper(Result=result, StatusCode=0, StatusMessage="Completed")
    except NodeFailure as exc:
        detail = exc.details[0] if exc.details and isinstance(exc.details[0], dict) else {}
        result = detail.get("output", context.partial or None)
        failure = {"type": exc.error_type, "retryable": not exc.non_retryable}
        wrapper = StandardOutputWrapper(
            Result=result, StatusCode=1, StatusMessage=exc.error_type[:500], ErrorMessage=str(exc)[:10000]
        )
    except asyncio.CancelledError:
        failure = {"type": "CancelledError", "retryable": False}
        wrapper = StandardOutputWrapper(Result=context.partial or None, StatusCode=1, StatusMessage="Cancelled")
    except Exception as exc:  # noqa: BLE001 - process boundary must return a safe terminal result
        # Validation and unknown exception messages can embed credentials.
        error_type = "ValidationError" if isinstance(exc, ValidationError) else type(exc).__name__
        failure = {"type": error_type, "retryable": False}
        wrapper = StandardOutputWrapper(
            Result=context.partial or None, StatusCode=1, StatusMessage=error_type, ErrorMessage="Node execution failed"
        )
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    frame = scrub(
        {"version": 1, "kind": "result", "result": wrapper.model_dump(mode="json"), "error": failure}, context.secrets
    )
    if len(json.dumps(frame).encode()) > MAX_FRAME_BYTES:
        frame = {
            "version": 1,
            "kind": "result",
            "result": StandardOutputWrapper(
                Result=None, StatusCode=1, StatusMessage="Output limit exceeded"
            ).model_dump(),
            "error": {"type": "OutputLimitError", "retryable": False},
        }
    context.logger.info("Node execution finished")
    writer(frame)
    return cast("dict[str, Any]", frame)
