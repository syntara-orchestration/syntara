"""Tests for AAP resource type enums."""

import pytest

from syntara.workflows.workflow_engine.models.aap_types import AAPResourceType


class TestAAPResourceType:
    """Test AAPResourceType enum and its properties."""

    def test_job_templates_value(self):
        """Test JOB_TEMPLATES enum value."""
        assert AAPResourceType.JOB_TEMPLATES == "job_templates"
        assert AAPResourceType.JOB_TEMPLATES.value == "job_templates"

    def test_workflow_job_templates_value(self):
        """Test WORKFLOW_JOB_TEMPLATES enum value."""
        assert AAPResourceType.WORKFLOW_JOB_TEMPLATES == "workflow_job_templates"
        assert AAPResourceType.WORKFLOW_JOB_TEMPLATES.value == "workflow_job_templates"

    def test_inventories_value(self):
        """Test INVENTORIES enum value."""
        assert AAPResourceType.INVENTORIES == "inventories"
        assert AAPResourceType.INVENTORIES.value == "inventories"

    def test_instance_groups_value(self):
        """Test INSTANCE_GROUPS enum value."""
        assert AAPResourceType.INSTANCE_GROUPS == "instance_groups"
        assert AAPResourceType.INSTANCE_GROUPS.value == "instance_groups"

    @pytest.mark.parametrize(
        ("resource_type", "expected_display_name"),
        [
            (AAPResourceType.JOB_TEMPLATES, "job template"),
            (AAPResourceType.WORKFLOW_JOB_TEMPLATES, "workflow job template"),
            (AAPResourceType.INVENTORIES, "inventory"),
            (AAPResourceType.INSTANCE_GROUPS, "instance group"),
        ],
    )
    def test_display_name(self, resource_type: AAPResourceType, expected_display_name: str):
        """Test display_name property returns correct singular form."""
        assert resource_type.display_name == expected_display_name

    @pytest.mark.parametrize(
        ("resource_type", "expected_plural"),
        [
            (AAPResourceType.JOB_TEMPLATES, "job templates"),
            (AAPResourceType.WORKFLOW_JOB_TEMPLATES, "workflow job templates"),
            (AAPResourceType.INVENTORIES, "inventories"),
            (AAPResourceType.INSTANCE_GROUPS, "instance groups"),
        ],
    )
    def test_display_name_plural(self, resource_type: AAPResourceType, expected_plural: str):
        """Test display_name_plural property returns correct plural form."""
        assert resource_type.display_name_plural == expected_plural

    @pytest.mark.parametrize(
        ("resource_type", "expected_prefix"),
        [
            (AAPResourceType.JOB_TEMPLATES, "job_template"),
            (AAPResourceType.WORKFLOW_JOB_TEMPLATES, "workflow_job_template"),
            (AAPResourceType.INVENTORIES, "inventory"),
            (AAPResourceType.INSTANCE_GROUPS, "instance_group"),
        ],
    )
    def test_field_prefix(self, resource_type: AAPResourceType, expected_prefix: str):
        """Test field_prefix property returns correct singular field name."""
        assert resource_type.field_prefix == expected_prefix
