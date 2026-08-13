"""Tests for integration_id field on AAP executor configs.

Validates that AAPJobTemplateExecutorParameters and AAPWorkflowJobTemplateExecutorParameters
accept, serialize, and validate the integration_id field using validate_uuid_or_template.
"""

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import (
    AAPJobTemplateExecutorParameters,
    AAPWorkflowJobTemplateExecutorParameters,
)

_VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"
_TEMPLATE_EXPR = "${input.integration}"


class TestAAPJobTemplateExecutorParametersIntegrationId:
    """Verify integration_id on AAPJobTemplateExecutorParameters."""

    def test_integration_id_accepts_valid_uuid(self) -> None:
        """Valid UUID string should be accepted."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=1,
            integration_id=_VALID_UUID,
        )
        assert config.integration_id == _VALID_UUID

    def test_integration_id_accepts_none(self) -> None:
        """None (default) should be accepted."""
        config = AAPJobTemplateExecutorParameters(job_template_id=1)
        assert config.integration_id is None

    def test_integration_id_accepts_template_expression(self) -> None:
        """Template expressions like ${...} should bypass UUID validation."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=1,
            integration_id=_TEMPLATE_EXPR,
        )
        assert config.integration_id == _TEMPLATE_EXPR

    def test_integration_id_rejects_invalid_string(self) -> None:
        """Non-UUID, non-template string should raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid UUID format"):
            AAPJobTemplateExecutorParameters(
                job_template_id=1,
                integration_id="not-a-uuid",
            )

    def test_integration_id_serializes(self) -> None:
        """integration_id should appear in model_dump output."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=1,
            integration_id=_VALID_UUID,
        )
        dumped = config.model_dump(by_alias=True)
        assert dumped["integration_id"] == _VALID_UUID

    def test_integration_id_deserializes_from_dict(self) -> None:
        """integration_id should deserialize from dict input."""
        config = AAPJobTemplateExecutorParameters.model_validate({"job_template_id": 1, "integration_id": _VALID_UUID})
        assert config.integration_id == _VALID_UUID

    def test_integration_id_coexists_with_credential_id(self) -> None:
        """integration_id and credential_id can be set simultaneously."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=1,
            integration_id=_VALID_UUID,
            credential_id="660e8400-e29b-41d4-a716-446655440000",
        )
        assert config.integration_id == _VALID_UUID
        assert config.credential_id == "660e8400-e29b-41d4-a716-446655440000"

    def test_backward_compat_without_integration_id(self) -> None:
        """Configs without integration_id should still parse (backward compatibility)."""
        config = AAPJobTemplateExecutorParameters.model_validate({"job_template_id": 1})
        assert config.integration_id is None


class TestAAPWorkflowJobTemplateExecutorParametersIntegrationId:
    """Verify integration_id on AAPWorkflowJobTemplateExecutorParameters."""

    def test_integration_id_accepts_valid_uuid(self) -> None:
        """Valid UUID string should be accepted."""
        config = AAPWorkflowJobTemplateExecutorParameters(
            workflow_job_template_id=1,
            integration_id=_VALID_UUID,
        )
        assert config.integration_id == _VALID_UUID

    def test_integration_id_accepts_none(self) -> None:
        """None (default) should be accepted."""
        config = AAPWorkflowJobTemplateExecutorParameters(workflow_job_template_id=1)
        assert config.integration_id is None

    def test_integration_id_accepts_template_expression(self) -> None:
        """Template expressions like ${...} should bypass UUID validation."""
        config = AAPWorkflowJobTemplateExecutorParameters(
            workflow_job_template_id=1,
            integration_id=_TEMPLATE_EXPR,
        )
        assert config.integration_id == _TEMPLATE_EXPR

    def test_integration_id_rejects_invalid_string(self) -> None:
        """Non-UUID, non-template string should raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid UUID format"):
            AAPWorkflowJobTemplateExecutorParameters(
                workflow_job_template_id=1,
                integration_id="not-a-uuid",
            )

    def test_integration_id_serializes(self) -> None:
        """integration_id should appear in model_dump output."""
        config = AAPWorkflowJobTemplateExecutorParameters(
            workflow_job_template_id=1,
            integration_id=_VALID_UUID,
        )
        dumped = config.model_dump(by_alias=True)
        assert dumped["integration_id"] == _VALID_UUID

    def test_integration_id_deserializes_from_dict(self) -> None:
        """integration_id should deserialize from dict input."""
        config = AAPWorkflowJobTemplateExecutorParameters.model_validate(
            {"workflow_job_template_id": 1, "integration_id": _VALID_UUID}
        )
        assert config.integration_id == _VALID_UUID

    def test_integration_id_coexists_with_credential_id(self) -> None:
        """integration_id and credential_id can be set simultaneously."""
        config = AAPWorkflowJobTemplateExecutorParameters(
            workflow_job_template_id=1,
            integration_id=_VALID_UUID,
            credential_id="660e8400-e29b-41d4-a716-446655440000",
        )
        assert config.integration_id == _VALID_UUID
        assert config.credential_id == "660e8400-e29b-41d4-a716-446655440000"

    def test_backward_compat_without_integration_id(self) -> None:
        """Configs without integration_id should still parse (backward compatibility)."""
        config = AAPWorkflowJobTemplateExecutorParameters.model_validate({"workflow_job_template_id": 1})
        assert config.integration_id is None
