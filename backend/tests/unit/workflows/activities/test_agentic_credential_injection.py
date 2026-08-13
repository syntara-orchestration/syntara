"""Tests for Agentic activity credential injection (T069).

Verifies that credential_id (not the decrypted key) is passed to
Agent Orchestrator via metadata for deferred resolution.
"""

from typing import Any

from syntara.workflows.workflow_engine.activities.agentic_activity import _inject_llm_credential_metadata


class TestAgenticCredentialMetadata:
    """Test LLM credential injection into agent metadata."""

    def test_credential_id_injected_not_api_key(self) -> None:
        """credential_id is injected; llm_api_key is NOT (security: no plaintext in context_data)."""
        metadata: dict[str, Any] = {"activity_name": "test"}
        input_data: dict[str, Any] = {
            "_resolved_credentials": {
                "credential_id": "cred-uuid-123",
                "extra_vars": {
                    "auth_type": "api_key",
                    "llm_api_key": "sk-ant-secret",
                },
            },
        }

        _inject_llm_credential_metadata(metadata, input_data)

        assert metadata["credential_id"] == "cred-uuid-123"
        assert "llm_api_key" not in metadata
        assert metadata["activity_name"] == "test"

    def test_no_credentials_no_metadata(self) -> None:
        """Without resolved credentials, metadata is unchanged."""
        metadata: dict[str, Any] = {"activity_name": "test"}

        _inject_llm_credential_metadata(metadata, {})

        assert "credential_id" not in metadata
        assert "llm_api_key" not in metadata
        assert metadata["activity_name"] == "test"

    def test_partial_credentials_no_credential_id(self) -> None:
        """Without credential_id, no credential metadata is added."""
        metadata: dict[str, Any] = {}
        input_data: dict[str, Any] = {
            "_resolved_credentials": {
                "extra_vars": {
                    "llm_api_key": "sk-partial-key",
                },
            },
        }

        _inject_llm_credential_metadata(metadata, input_data)

        assert "credential_id" not in metadata
        assert "llm_api_key" not in metadata

    def test_secret_fields_not_injected(self) -> None:
        """Only credential_id is passed; secret LLM fields are not injected into metadata."""
        metadata: dict[str, Any] = {}
        input_data: dict[str, Any] = {
            "_resolved_credentials": {
                "credential_id": "cred-456",
                "extra_vars": {
                    "llm_api_key": "sk-secret-key",
                },
            },
        }

        _inject_llm_credential_metadata(metadata, input_data)

        assert metadata["credential_id"] == "cred-456"
        assert "llm_api_key" not in metadata
