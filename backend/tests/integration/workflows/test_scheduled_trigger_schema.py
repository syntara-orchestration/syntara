"""Contract tests for scheduled trigger JSON schema.

Validates that the scheduled trigger schema file is well-formed and accepts/rejects
the expected configurations.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas" / "workflows" / "v2" / "triggers"


@pytest.fixture
def scheduled_schema() -> dict[str, Any]:
    """Load the scheduled trigger schema."""
    schema_path = SCHEMA_DIR / "scheduled.schema.json"
    with schema_path.open() as f:
        result: dict[str, Any] = json.load(f)
        return result


async def test_scheduled_schema_has_config_schema(scheduled_schema: dict[str, Any]) -> None:
    """Schema should have a parameterSchema section."""
    assert "parameterSchema" in scheduled_schema


async def test_scheduled_schema_has_result_schema(scheduled_schema: dict[str, Any]) -> None:
    """Schema should have a resultSchema section."""
    assert "resultSchema" in scheduled_schema


async def test_scheduled_config_requires_schedule_type(scheduled_schema: dict[str, Any]) -> None:
    """Config schema should require schedule_type."""
    config_schema = scheduled_schema["parameterSchema"]
    assert "schedule_type" in config_schema.get("required", [])


async def test_scheduled_config_valid_cron(scheduled_schema: dict[str, Any]) -> None:
    """Cron config with schedule_type and cron should be valid."""
    config = {"schedule_type": "cron", "cron": "0 9 * * *"}
    jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_valid_cron_with_timezone(scheduled_schema: dict[str, Any]) -> None:
    """Cron config with timezone should be valid."""
    config = {"schedule_type": "cron", "cron": "0 9 * * *", "timezone": "America/New_York"}
    jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_valid_interval(scheduled_schema: dict[str, Any]) -> None:
    """Interval config with schedule_type and interval should be valid."""
    config = {"schedule_type": "interval", "interval": "R/2024-01-01T10:00:00Z/P1D"}
    jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_valid_with_missed_policy(scheduled_schema: dict[str, Any]) -> None:
    """Config with missed_schedule_policy should be valid."""
    config = {
        "schedule_type": "cron",
        "cron": "0 9 * * *",
        "missed_schedule_policy": "buffer_one",
    }
    jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_rejects_missing_schedule_type(scheduled_schema: dict[str, Any]) -> None:
    """Config without schedule_type should be rejected."""
    config = {"cron": "0 9 * * *"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_rejects_invalid_schedule_type(scheduled_schema: dict[str, Any]) -> None:
    """Config with invalid schedule_type should be rejected."""
    config = {"schedule_type": "hourly", "interval": "PT1H"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_rejects_additional_properties(scheduled_schema: dict[str, Any]) -> None:
    """Config with unknown properties should be rejected."""
    config = {"schedule_type": "cron", "cron": "0 9 * * *", "unknown_field": "value"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_rejects_invalid_missed_policy(scheduled_schema: dict[str, Any]) -> None:
    """Config with invalid missed_schedule_policy should be rejected."""
    config = {
        "schedule_type": "cron",
        "cron": "0 9 * * *",
        "missed_schedule_policy": "retry",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_requires_interval_for_interval_type(scheduled_schema: dict[str, Any]) -> None:
    """Interval schedule_type without interval field should be rejected."""
    config = {"schedule_type": "interval"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_config_requires_cron_for_cron_type(scheduled_schema: dict[str, Any]) -> None:
    """Cron schedule_type without cron field should be rejected."""
    config = {"schedule_type": "cron"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=scheduled_schema["parameterSchema"])


async def test_scheduled_trigger_in_workflow_definition_schema() -> None:
    """Scheduled trigger should be listed in the workflow definition schema."""
    schema_path = SCHEMA_DIR.parent / "workflow_definition.schema.json"
    with schema_path.open() as f:
        wf_schema = json.load(f)

    trigger_node = wf_schema["$defs"]["trigger_node"]
    one_of = trigger_node["oneOf"]

    scheduled_entries = [
        entry
        for entry in one_of
        if any(
            allof_item.get("properties", {}).get("type", {}).get("const") == "scheduled_trigger"
            for allof_item in entry.get("allOf", [])
        )
    ]
    assert len(scheduled_entries) == 1


async def test_scheduled_trigger_in_node_type_catalog() -> None:
    """Scheduled trigger should be listed in the node type catalog."""
    catalog_path = SCHEMA_DIR.parent / "catalog" / "node_type_catalog.json"
    with catalog_path.open() as f:
        catalog = json.load(f)

    scheduled_types = [nt for nt in catalog["node_types"] if nt["type"] == "scheduled_trigger"]
    assert len(scheduled_types) == 1
    assert scheduled_types[0]["labels"]["category"] == "trigger"
