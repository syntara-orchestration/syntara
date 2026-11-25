"""Tests for Execution Plane execution profiles on executor parameters."""

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from syntara.workflow_core.models import (
    BashScriptExecutorParameters,
    ExecutionTargetProfile,
)


class TestBashScriptExecutorParametersExecutionProfile:
    """Validate the discriminated Execution Plane profile on Script parameters."""

    def test_accepts_execution_target_profile(self) -> None:
        """An Execution Target profile is parsed into its concrete profile type."""
        execution_target_id = uuid4()

        config = BashScriptExecutorParameters(
            code=":",
            execution_profile=ExecutionTargetProfile(
                type="execution_target",
                execution_target_id=execution_target_id,
            ),
        )

        assert config.execution_profile == ExecutionTargetProfile(
            type="execution_target",
            execution_target_id=execution_target_id,
        )
        assert isinstance(config.execution_profile, ExecutionTargetProfile)
        assert config.execution_profile.execution_target_id == execution_target_id
        assert isinstance(config.execution_profile.execution_target_id, UUID)

    def test_defaults_to_none(self) -> None:
        """Omitting the field preserves existing Script node definitions."""
        config = BashScriptExecutorParameters(code=":")

        assert config.execution_profile is None

    def test_serializes_profile_as_json(self) -> None:
        """JSON serialization keeps the discriminator and UUID portable."""
        execution_target_id = uuid4()
        config = BashScriptExecutorParameters(
            code=":",
            execution_profile=ExecutionTargetProfile(
                type="execution_target",
                execution_target_id=execution_target_id,
            ),
        )

        assert config.model_dump(mode="json")["execution_profile"] == {
            "type": "execution_target",
            "execution_target_id": str(execution_target_id),
        }

    def test_rejects_invalid_uuid(self) -> None:
        """A non-UUID value is rejected."""
        with pytest.raises(ValidationError, match="execution_target_id"):
            BashScriptExecutorParameters.model_validate(
                {
                    "code": ":",
                    "execution_profile": {"type": "execution_target", "execution_target_id": "not-a-uuid"},
                }
            )

    def test_rejects_unknown_profile_type(self) -> None:
        """An unknown discriminator value is rejected."""
        with pytest.raises(ValidationError, match="execution_profile"):
            BashScriptExecutorParameters.model_validate(
                {
                    "code": ":",
                    "execution_profile": {"type": "automatic", "execution_target_id": str(uuid4())},
                }
            )

    def test_json_schema_uses_discriminated_profile_union(self) -> None:
        """The model schema exposes the profile as a discriminated oneOf union."""
        profile_schema = BashScriptExecutorParameters.model_json_schema()["properties"]["execution_profile"]

        assert profile_schema["anyOf"][0]["oneOf"] == [{"$ref": "#/$defs/ExecutionTargetProfile"}]
        assert profile_schema["anyOf"][0]["discriminator"] == {
            "mapping": {"execution_target": "#/$defs/ExecutionTargetProfile"},
            "propertyName": "type",
        }
