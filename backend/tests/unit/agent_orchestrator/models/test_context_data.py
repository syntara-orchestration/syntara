"""Unit tests for InvocationContextData and InvocationMetadata typed models."""

from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from syntara.agent_orchestrator.models.context_data import (
    InvocationContextData,
    InvocationMetadata,
    OpaqueResponseSchema,
)


class TestInvocationMetadata:
    """Tests for InvocationMetadata model."""

    def test_minimal_construction(self) -> None:
        meta = InvocationMetadata()
        assert meta.credential_id is None
        assert meta.response_schema is None
        assert meta.request_id is None

    def test_full_construction(self) -> None:
        meta = InvocationMetadata(
            credential_id=SecretStr("cred-123"),
            response_schema=OpaqueResponseSchema({"type": "object"}),
            request_id="req-456",
        )
        assert meta.credential_id is not None
        assert meta.credential_id.get_secret_value() == "cred-123"
        assert meta.response_schema is not None
        assert meta.response_schema.get_data() == {"type": "object"}

    def test_secret_str_from_raw_dict(self) -> None:
        """model_validate auto-wraps plain strings into SecretStr."""
        meta = InvocationMetadata.model_validate({"credential_id": "cred-1"})
        assert isinstance(meta.credential_id, SecretStr)
        assert meta.credential_id.get_secret_value() == "cred-1"

    def test_secret_str_masked_in_repr(self) -> None:
        meta = InvocationMetadata.model_validate({"credential_id": "secret-cred"})
        assert "secret-cred" not in repr(meta)

    def test_audit_safe_dump_excludes_sensitive_fields(self) -> None:
        meta = InvocationMetadata.model_validate(
            {
                "credential_id": "cred-123",
                "response_schema": {"type": "object"},
                "request_id": "req-456",
            }
        )
        safe = meta.audit_safe_dump()

        assert "credential_id" not in safe
        assert "response_schema" not in safe
        assert safe["request_id"] == "req-456"

    def test_extra_fields_ignored(self) -> None:
        meta = InvocationMetadata.model_validate({"custom_key": "custom_value"})
        assert "custom_key" not in meta.model_dump()


_UUID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_UUID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class TestInvocationMetadataToolSelection:
    """Tests for InvocationMetadata.tool_selection_strategy and tool_selections fields."""

    def test_tool_selection_defaults(self) -> None:
        meta = InvocationMetadata()
        assert meta.tool_selection_strategy is None
        assert meta.tool_selections == []

    def test_tool_selection_round_trip(self) -> None:
        meta = InvocationMetadata.model_validate(
            {"tool_selection_strategy": "SELECTED", "tool_selections": [_UUID_A, _UUID_B]}
        )
        assert meta.tool_selection_strategy == "SELECTED"
        assert meta.tool_selections == [_UUID_A, _UUID_B]

    def test_strategy_present_selections_absent_defaults_to_empty(self) -> None:
        meta = InvocationMetadata.model_validate({"tool_selection_strategy": "NONE"})
        assert meta.tool_selection_strategy == "NONE"
        assert meta.tool_selections == []

    def test_all_strategy_round_trip(self) -> None:
        meta = InvocationMetadata.model_validate({"tool_selection_strategy": "ALL"})
        assert meta.tool_selection_strategy == "ALL"

    def test_tool_selections_included_in_to_state_dict(self) -> None:
        ctx = InvocationContextData.model_validate(
            {"metadata": {"tool_selection_strategy": "SELECTED", "tool_selections": [_UUID_A]}}
        )
        assert ctx.metadata is not None
        state = ctx.to_state_dict()
        assert state["metadata"]["tool_selection_strategy"] == "SELECTED"
        assert state["metadata"]["tool_selections"] == [_UUID_A]

    def test_tool_selection_included_in_audit_safe_dump(self) -> None:
        meta = InvocationMetadata.model_validate({"tool_selection_strategy": "SELECTED", "tool_selections": [_UUID_A]})
        safe = meta.audit_safe_dump()
        assert safe["tool_selection_strategy"] == "SELECTED"
        assert safe["tool_selections"] == [_UUID_A]

    def test_selected_with_empty_tools_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"must not be empty"):
            InvocationMetadata.model_validate({"tool_selection_strategy": "SELECTED", "tool_selections": []})

    def test_none_strategy_with_tools_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"must be empty"):
            InvocationMetadata.model_validate({"tool_selection_strategy": "NONE", "tool_selections": [_UUID_A]})

    def test_all_strategy_with_tools_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"must be empty"):
            InvocationMetadata.model_validate({"tool_selection_strategy": "ALL", "tool_selections": [_UUID_A]})

    def test_none_default_strategy_with_tools_rejected(self) -> None:
        """strategy=None (default) with non-empty tools is rejected."""
        with pytest.raises(ValidationError, match=r"must be empty"):
            InvocationMetadata.model_validate({"tool_selections": [_UUID_A]})

    def test_invalid_tool_uuid_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"Invalid UUID"):
            InvocationMetadata.model_validate(
                {"tool_selection_strategy": "SELECTED", "tool_selections": ["not-a-uuid"]}
            )


class TestInvocationContextData:
    """Tests for InvocationContextData model."""

    def test_minimal_construction(self) -> None:
        ctx = InvocationContextData()
        assert ctx.file_ids == []
        assert ctx.agent is None
        assert ctx.model is None
        assert ctx.workflow_id is None
        assert ctx.activity_id is None
        assert ctx.activity_name is None
        assert ctx.execution_id is None
        assert ctx.metadata is None

    def test_from_raw_dict(self) -> None:
        raw: dict[str, Any] = {
            "file_ids": ["id-1", "id-2"],
            "agent": "workflow-agent",
            "model": "gpt-4",
            "callback_url": "https://example.com/cb",
            "metadata": {
                "request_id": "req-1",
                "credential_id": "cred-1",
            },
        }
        ctx = InvocationContextData.model_validate(raw)
        assert ctx.file_ids == ["id-1", "id-2"]
        assert ctx.agent == "workflow-agent"
        assert isinstance(ctx.callback_url, SecretStr)
        assert ctx.callback_url.get_secret_value() == "https://example.com/cb"
        assert ctx.metadata is not None
        assert ctx.metadata.request_id == "req-1"
        assert ctx.metadata.credential_id is not None
        assert ctx.metadata.credential_id.get_secret_value() == "cred-1"

    def test_audit_safe_metadata(self) -> None:
        ctx = InvocationContextData.model_validate(
            {
                "metadata": {
                    "credential_id": "cred-secret",
                    "response_schema": {"type": "string"},
                    "request_id": "req-visible",
                }
            }
        )
        safe = ctx.audit_safe_metadata()
        assert "credential_id" not in safe
        assert "response_schema" not in safe
        assert safe["request_id"] == "req-visible"

    def test_audit_safe_metadata_when_none(self) -> None:
        ctx = InvocationContextData()
        assert ctx.audit_safe_metadata() == {}

    def test_extra_fields_preserved(self) -> None:
        raw: dict[str, Any] = {"file_ids": [], "environment": "production", "region": "us-east-1"}
        ctx = InvocationContextData.model_validate(raw)
        dumped = ctx.model_dump()
        assert dumped["environment"] == "production"
        assert dumped["region"] == "us-east-1"

    def test_empty_dict_validation(self) -> None:
        ctx = InvocationContextData.model_validate({})
        assert ctx.file_ids == []
        assert ctx.metadata is None

    def test_round_trip_preserves_data(self) -> None:
        """model_validate -> model_dump round-trip preserves all fields."""
        raw: dict[str, Any] = {
            "file_ids": ["f1"],
            "agent": "test-agent",
            "model": "gpt-4",
            "callback_url": "https://cb.example.com",
            "input_data": {"key": "val"},
            "workflow_id": "w1",
            "activity_id": "a1",
            "activity_name": "agentic_v2",
            "execution_id": "e1",
            "metadata": {
                "credential_id": "c1",
                "response_schema": {"type": "object"},
                "request_id": "r1",
            },
        }
        ctx = InvocationContextData.model_validate(raw)
        assert ctx.callback_url is not None
        assert ctx.callback_url.get_secret_value() == "https://cb.example.com"
        assert ctx.metadata is not None
        assert ctx.metadata.credential_id is not None
        assert ctx.metadata.credential_id.get_secret_value() == "c1"
        assert ctx.metadata.response_schema is not None
        assert ctx.metadata.response_schema.get_data() == {"type": "object"}

        # Verify round-trip: dump and re-validate produces equivalent data
        dumped = ctx.model_dump()
        ctx2 = InvocationContextData.model_validate(dumped)
        assert ctx2.file_ids == ["f1"]
        assert ctx2.agent == "test-agent"
        assert ctx2.model == "gpt-4"
        assert ctx2.callback_url is not None
        assert ctx2.callback_url.get_secret_value() == "https://cb.example.com"
        assert ctx2.input_data == {"key": "val"}
        assert ctx2.workflow_id == "w1"
        assert ctx2.activity_id == "a1"
        assert ctx2.activity_name == "agentic_v2"
        assert ctx2.execution_id == "e1"
        assert ctx2.metadata is not None
        assert ctx2.metadata.credential_id is not None
        assert ctx2.metadata.credential_id.get_secret_value() == "c1"
        assert ctx2.metadata.response_schema is not None
        assert ctx2.metadata.response_schema.get_data() == {"type": "object"}
        assert ctx2.metadata.request_id == "r1"

    def test_top_level_callback_url_is_secret(self) -> None:
        ctx = InvocationContextData.model_validate({"callback_url": "https://secret-cb.com"})
        assert isinstance(ctx.callback_url, SecretStr)
        assert "https://secret-cb.com" not in repr(ctx)

    def test_metadata_rejects_invalid_type(self) -> None:
        """Metadata must be dict, InvocationMetadata, or None — not a list or string."""
        with pytest.raises(ValidationError, match="metadata must be a dict"):
            InvocationContextData.model_validate({"metadata": ["not", "a", "dict"]})

        with pytest.raises(ValidationError, match="metadata must be a dict"):
            InvocationContextData.model_validate({"metadata": "bad"})

    def test_workflow_execution_context_fields(self) -> None:
        """Workflow/execution context fields are properly validated and serialized."""
        ctx = InvocationContextData.model_validate(
            {
                "workflow_id": "wf-123",
                "execution_id": "exec-456",
                "activity_id": "act-789",
                "activity_name": "process_data",
            }
        )
        assert ctx.workflow_id == "wf-123"
        assert ctx.execution_id == "exec-456"
        assert ctx.activity_id == "act-789"
        assert ctx.activity_name == "process_data"

        # Verify serialization
        dumped = ctx.model_dump()
        assert dumped["workflow_id"] == "wf-123"
        assert dumped["execution_id"] == "exec-456"
        assert dumped["activity_id"] == "act-789"
        assert dumped["activity_name"] == "process_data"

    def test_timeout_seconds_parsed_from_raw_dict(self) -> None:
        """Validates timeout_seconds=120 from raw dict."""
        ctx = InvocationContextData.model_validate({"timeout_seconds": 120})
        assert ctx.timeout_seconds == 120

    def test_timeout_seconds_defaults_to_none(self) -> None:
        """Defaults to None when not provided."""
        ctx = InvocationContextData.model_validate({})
        assert ctx.timeout_seconds is None

    def test_workflow_execution_context_fields_optional(self) -> None:
        """Workflow/execution context fields are optional and default to None."""
        ctx = InvocationContextData.model_validate({"agent": "test"})
        assert ctx.workflow_id is None
        assert ctx.execution_id is None
        assert ctx.activity_id is None
        assert ctx.activity_name is None

        # None values excluded when exclude_none=True
        dumped = ctx.model_dump(exclude_none=True)
        assert "workflow_id" not in dumped
        assert "execution_id" not in dumped
        assert "activity_id" not in dumped
        assert "activity_name" not in dumped

    def test_to_state_dict_includes_context_fields(self) -> None:
        """to_state_dict includes workflow/execution context fields."""
        ctx = InvocationContextData.model_validate(
            {
                "agent": "test-agent",
                "workflow_id": "wf-999",
                "execution_id": "exec-888",
                "activity_id": "act-777",
                "activity_name": "validate",
                "callback_url": "https://example.com/callback",
            }
        )
        state_dict = ctx.to_state_dict()

        # Verify context fields are in state dict
        assert state_dict["workflow_id"] == "wf-999"
        assert state_dict["execution_id"] == "exec-888"
        assert state_dict["activity_id"] == "act-777"
        assert state_dict["activity_name"] == "validate"

        # Verify callback_url is revealed (not SecretStr)
        assert state_dict["callback_url"] == "https://example.com/callback"
        assert isinstance(state_dict["callback_url"], str)


class TestOpaqueResponseSchema:
    """Tests for OpaqueResponseSchema wrapper type."""

    def test_get_data_returns_wrapped_value(self) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        opaque = OpaqueResponseSchema(schema)
        assert opaque.get_data() == schema

    def test_repr_hides_data(self) -> None:
        opaque = OpaqueResponseSchema({"type": "object", "secret": "large-payload"})
        assert repr(opaque) == "OpaqueResponseSchema(**)"
        assert str(opaque) == "OpaqueResponseSchema(**)"
        assert "large-payload" not in repr(opaque)

    def test_equality(self) -> None:
        a = OpaqueResponseSchema({"type": "object"})
        b = OpaqueResponseSchema({"type": "object"})
        c = OpaqueResponseSchema({"type": "string"})
        assert a == b
        assert a != c

    def test_model_validate_wraps_dict(self) -> None:
        """model_validate auto-wraps raw dicts into OpaqueResponseSchema."""
        meta = InvocationMetadata.model_validate({"response_schema": {"type": "object"}})
        assert isinstance(meta.response_schema, OpaqueResponseSchema)
        assert meta.response_schema.get_data() == {"type": "object"}

    def test_model_dump_unwraps(self) -> None:
        """model_dump serializes OpaqueResponseSchema back to the raw value."""
        meta = InvocationMetadata.model_validate({"response_schema": {"type": "object"}})
        dumped = meta.model_dump()
        assert dumped["response_schema"] == {"type": "object"}

    def test_excluded_from_audit_safe_dump(self) -> None:
        meta = InvocationMetadata.model_validate({"response_schema": {"type": "object"}, "request_id": "r1"})
        safe = meta.audit_safe_dump()
        assert "response_schema" not in safe
        assert safe["request_id"] == "r1"

    def test_none_response_schema(self) -> None:
        meta = InvocationMetadata()
        assert meta.response_schema is None

    def test_rejects_non_dict(self) -> None:
        with pytest.raises(ValidationError, match="response_schema must be a dict"):
            InvocationMetadata.model_validate({"response_schema": "not-a-dict"})

    def test_accepts_missing_type_field_per_draft07(self) -> None:
        """Schema without 'type' is valid per JSON Schema Draft-07."""
        meta = InvocationMetadata.model_validate({"response_schema": {"properties": {}}})
        assert meta.response_schema is not None

    def test_rejects_ref_for_ssrf_prevention(self) -> None:
        with pytest.raises(ValidationError, match="\\$ref"):
            InvocationMetadata.model_validate(
                {"response_schema": {"type": "object", "properties": {"x": {"$ref": "https://evil.com"}}}}
            )


class TestInvocationMetadataIntegrationConnections:
    """Tests for InvocationMetadata.integration_connections field.

    integration_connections is declared on InvocationMetadata (not on
    InvocationContextData top-level) because agentic_activity places it
    inside agent_metadata, which the agent client routes to contextData.metadata.
    InvocationMetadata uses extra="ignore" so fields must be declared here
    to survive the round-trip.
    """

    def test_integration_connections_defaults_to_none(self) -> None:
        meta = InvocationMetadata.model_validate({})
        assert meta.integration_connections is None

    def test_integration_connections_round_trip(self) -> None:
        from syntara.workflows.workflow_engine.models.workflow_definition import IntegrationConnectionConfig

        connections = [
            {
                "integration_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "credential_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            },
            {
                "integration_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "credential_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            },
        ]
        meta = InvocationMetadata.model_validate({"integration_connections": connections})
        assert meta.integration_connections == [
            IntegrationConnectionConfig(
                integration_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                credential_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
            ),
            IntegrationConnectionConfig(
                integration_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                credential_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
            ),
        ]

    def test_integration_connections_surfaced_via_ctx_metadata(self) -> None:
        """integration_connections in contextData.metadata is accessible via ctx.metadata."""
        from syntara.workflows.workflow_engine.models.workflow_definition import IntegrationConnectionConfig

        connections = [
            {
                "integration_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "credential_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            }
        ]
        ctx = InvocationContextData.model_validate({"metadata": {"integration_connections": connections}})
        assert ctx.metadata is not None
        assert ctx.metadata.integration_connections == [
            IntegrationConnectionConfig(
                integration_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                credential_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            )
        ]

    def test_integration_connections_absent_from_audit_safe_dump(self) -> None:
        """integration_connections=None is excluded when exclude_none=True."""
        meta = InvocationMetadata.model_validate({})
        dumped = meta.audit_safe_dump()
        assert "integration_connections" not in dumped
