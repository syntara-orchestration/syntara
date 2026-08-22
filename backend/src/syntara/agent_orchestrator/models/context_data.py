"""Typed models for invocation context_data.

These models provide type-safe access to the context_data JSONB field on
Invocation records.  The DB column stays ``dict[str, object]`` (JSONB) for
backward compatibility; these models are used at the application layer for
validation, typed attribute access, and audit-safe serialization.

Usage::

    ctx = InvocationContextData.model_validate(invocation.context_data)
    ctx.metadata.credential_id   # typed access
    ctx.metadata.audit_safe_dump()  # excludes sensitive fields
"""

from typing import Any, Literal, get_args

import structlog
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_core import CoreSchema, core_schema

from syntara.workflows.json_schema_validation import validate_json_schema_definition
from syntara.workflows.workflow_engine.models.workflow_definition import (
    IntegrationConnectionConfig,
    validate_tool_selection_coherence,
    validate_uuid_or_template,
)

logger = structlog.stdlib.get_logger(__name__)


class OpaqueResponseSchema:
    """Wrapper that hides a response schema dict from repr / logs.

    Similar to ``SecretStr`` but for JSON Schema dicts.  The data is only
    returned when explicitly requested via :meth:`get_data`.

    Validates the schema against JSON Schema Draft-07 meta-schema, rejects
    ``$ref`` references (SSRF prevention), and detects ReDoS-vulnerable
    regex patterns via ``validate_json_schema_definition()``.

    ``repr()`` / ``str()`` always return ``'OpaqueResponseSchema(**)'`` so
    the payload never leaks into audit logs, telemetry, or error messages.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        """Wrap a response schema dict."""
        self._data = data

    def get_data(self) -> dict[str, Any]:
        """Return the wrapped schema dict."""
        return self._data

    def __repr__(self) -> str:  # noqa: D105
        return "OpaqueResponseSchema(**)"

    def __str__(self) -> str:  # noqa: D105
        return "OpaqueResponseSchema(**)"

    def __eq__(self, other: object) -> bool:  # noqa: D105
        if isinstance(other, OpaqueResponseSchema):
            return self._data == other._data
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]  # mutable wrapper — unhashable

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,  # noqa: ANN401
        _handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        """Accept a valid JSON Schema dict and wrap it in OpaqueResponseSchema."""
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize,
                info_arg=False,
            ),
        )

    @classmethod
    def _validate(cls, v: object) -> "OpaqueResponseSchema":
        if isinstance(v, cls):
            return v
        if not isinstance(v, dict):
            msg = f"response_schema must be a dict; got {type(v).__name__}"
            raise ValueError(msg)  # noqa: TRY004 — Pydantic requires ValueError
        try:
            validate_json_schema_definition(v)
        except ValueError as e:
            msg = f"response_schema: {e}"
            logger.warning(
                "Config validation failed", source="OpaqueResponseSchema", field="response_schema", reason=str(e)
            )
            raise ValueError(msg) from None
        return cls(v)

    @staticmethod
    def _serialize(v: "OpaqueResponseSchema") -> dict[str, Any]:
        return v.get_data()


_HIDDEN_TYPES = (SecretStr, OpaqueResponseSchema)


def _hidden_field_names(model: type[BaseModel]) -> set[str]:
    """Return the names of all fields whose type includes a hidden type."""
    hidden = set()
    for name, info in model.model_fields.items():
        types_to_check = get_args(info.annotation) or (info.annotation,)
        if any(t in _HIDDEN_TYPES for t in types_to_check):
            hidden.add(name)
    return hidden


class InvocationMetadata(BaseModel):
    """Nested metadata within invocation context_data.

    Fields typed as ``SecretStr`` or ``OpaqueResponseSchema`` are
    automatically excluded from :meth:`audit_safe_dump` so they never
    appear in audit logs or telemetry.

    IMPORTANT: This model uses Pydantic's default ``extra="ignore"``.
    Any key present in ``contextData.metadata`` that is not declared here
    is silently discarded during ``model_validate``. Fields that need to
    survive the agentic_activity → agent_orchestrator_client → executor
    round-trip MUST be declared explicitly in this class.
    """

    # Sensitive — excluded from audit logs and masked in repr
    credential_id: SecretStr | None = None
    response_schema: OpaqueResponseSchema | None = None

    # Non-sensitive
    request_id: str | None = None
    llm_model_id: str | None = None
    tool_selection_strategy: Literal["ALL", "NONE", "SELECTED"] | None = None
    tool_selections: list[str] = Field(default_factory=list)
    integration_connections: list[IntegrationConnectionConfig] | None = None

    @field_validator("tool_selections")
    @classmethod
    def validate_tool_selections_uuids(cls, v: list[str]) -> list[str]:
        """Validate each tool_selection is a valid UUID or template expression."""
        for i, tool_id in enumerate(v):
            validate_uuid_or_template(tool_id, f"tool_selections[{i}]")
        return v

    @model_validator(mode="after")
    def _validate_tool_selection_coherence(self) -> "InvocationMetadata":
        """Validate that tool_selection_strategy and tool_selections are coherent."""
        validate_tool_selection_coherence(self.tool_selection_strategy, self.tool_selections, "InvocationMetadata")
        return self

    def audit_safe_dump(self) -> dict[str, Any]:
        """Return metadata dict with sensitive/opaque fields excluded."""
        return self.model_dump(
            exclude=_hidden_field_names(type(self)),
            exclude_none=True,
        )


class InvocationContextData(BaseModel):
    """Typed representation of ``Invocation.context_data``.

    The DB column remains ``dict[str, object]`` (JSONB).  Construct via::

        ctx = InvocationContextData.model_validate(raw_dict)

    Unknown keys are preserved thanks to ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow")

    file_ids: list[str] = Field(default_factory=list)
    agent: str | None = None
    model: str | None = None
    workflow_id: str | None = None
    activity_id: str | None = None
    activity_name: str | None = None
    execution_id: str | None = None
    callback_url: SecretStr | None = None
    timeout_seconds: int | None = None
    input_data: dict[str, Any] | None = None
    metadata: InvocationMetadata | None = None

    @field_validator("metadata", mode="before")
    @classmethod
    def _validate_metadata(cls, v: object) -> object:
        """Accept only dicts/InvocationMetadata for metadata; reject anything else."""
        if v is None or isinstance(v, (dict, InvocationMetadata)):
            return v
        msg = f"metadata must be a dict, InvocationMetadata, or None; got {type(v).__name__}"
        raise ValueError(msg)

    def to_state_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict with secrets revealed.

        Used when passing context_data into ``AgentState.metadata``
        (a LangGraph TypedDict that requires JSON-serializable values).
        """
        d = self.model_dump(mode="json")
        if self.callback_url:
            d["callback_url"] = self.callback_url.get_secret_value()
        return d

    def audit_safe_metadata(self) -> dict[str, Any]:
        """Return metadata dict with SecretStr fields excluded, for audit logging."""
        if self.metadata is None:
            return {}
        return self.metadata.audit_safe_dump()
