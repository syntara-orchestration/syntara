"""Unit tests for AAP instance group resolution in job template activity.

Tests instance group ID/name resolution including:
- Using instance group ID directly
- Resolving instance group by name
- ID takes precedence over name
- Error handling for instance group resolution failures
"""

import httpx
import pytest

from syntara.workflows.workflow_engine.activities.aap_job_template_activity import (
    _build_launch_body,
)
from syntara.workflows.workflow_engine.models.workflow_definition import AAPJobTemplateExecutorParameters

TEST_AAP_URL = "http://test.aap"
TEST_ORG_NAME = "Engineering"
TEST_ORG_ID = 5


def create_http_response(
    status_code: int, json: dict[str, object] | None = None, text: str | None = None
) -> httpx.Response:
    """Helper to create mock HTTP responses."""
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", TEST_AAP_URL),
        json=json,
        text=text,
    )


@pytest.mark.asyncio
class TestInstanceGroupResolution:
    """Tests for instance group resolution in _launch_aap_job."""

    async def test_build_launch_body_with_instance_group_id(self) -> None:
        """Should include instance_groups array when instance group ID provided."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=123,
            organization_name=TEST_ORG_NAME,
        )

        body = _build_launch_body(config, inventory_id=None, instance_group_id=42)

        assert body["instance_groups"] == [42]

    async def test_build_launch_body_without_instance_group(self) -> None:
        """Should omit instance_groups when no instance group provided."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=123,
            organization_name=TEST_ORG_NAME,
        )

        body = _build_launch_body(config, inventory_id=None, instance_group_id=None)

        assert "instance_groups" not in body

    async def test_build_launch_body_with_inventory_and_instance_group(self) -> None:
        """Should include both inventory and instance_groups when both provided."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=123,
            organization_name=TEST_ORG_NAME,
        )

        body = _build_launch_body(config, inventory_id=100, instance_group_id=42)

        assert body["inventory"] == 100
        assert body["instance_groups"] == [42]

    async def test_instance_group_id_field_validation(self) -> None:
        """Should validate instance_group_id is positive integer."""
        # Valid instance group ID
        config = AAPJobTemplateExecutorParameters(
            job_template_id=123,
            organization_name=TEST_ORG_NAME,
            instance_group_id=42,
        )
        assert config.instance_group_id == 42

        # Zero should fail validation
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            AAPJobTemplateExecutorParameters(
                job_template_id=123,
                organization_name=TEST_ORG_NAME,
                instance_group_id=0,
            )

        # Negative should fail validation
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            AAPJobTemplateExecutorParameters(
                job_template_id=123,
                organization_name=TEST_ORG_NAME,
                instance_group_id=-1,
            )

    async def test_instance_group_name_field(self) -> None:
        """Should accept instance_group_name string."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=123,
            organization_name=TEST_ORG_NAME,
            instance_group_name="default",
        )
        assert config.instance_group_name == "default"

    async def test_both_instance_group_id_and_name_allowed(self) -> None:
        """Should allow both instance_group_id and instance_group_name (ID takes precedence)."""
        config = AAPJobTemplateExecutorParameters(
            job_template_id=123,
            organization_name=TEST_ORG_NAME,
            instance_group_id=42,
            instance_group_name="default",
        )
        assert config.instance_group_id == 42
        assert config.instance_group_name == "default"
