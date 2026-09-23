"""Tests for node_settings_resolver pure functions."""

import pytest
from pydantic import ValidationError

from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.workflows.workflow_engine.constants import DEFAULT_MAX_OUTPUT_BYTES
from syntara.workflows.workflow_engine.graph import ActivityNode
from syntara.workflows.workflow_engine.models.workflow_definition import NodeSettingsCof, NodeSettingsNoRetry
from syntara.workflows.workflow_engine.node_settings_resolver import (
    resolve_expected_duration,
    resolve_max_output_bytes,
    resolve_retry_policy,
)


def _catalog_defaults() -> dict[str, object]:
    return {e.key: e.default_value for e in SETTINGS_CATALOG if e.key.startswith("workflow_engine.")}


def test_resolve_retry_policy_inline_fallbacks_match_catalog_defaults() -> None:
    """Inline fallbacks in resolve_retry_policy must stay in sync with catalog defaults.

    resolve_retry_policy is called with an empty runtime_settings dict (simulating a
    total cache miss) and again with the full catalog defaults. Both calls must produce
    an identical RetryPolicy, proving the hardcoded fallbacks are exact mirrors of the
    catalog entries. If a catalog default is changed without updating the inline
    fallback (or vice versa), this test fails.
    """
    node = ActivityNode(node_id="n", node_type="script", parameters={})

    result_inline = resolve_retry_policy(node, {})
    result_catalog = resolve_retry_policy(node, _catalog_defaults())

    assert result_inline == result_catalog, (
        "Inline fallbacks in resolve_retry_policy diverged from catalog defaults. "
        "Update the hardcoded fallback values in node_settings_resolver.py to match "
        "the default_value entries in settings/catalog.py."
    )


def test_resolve_max_output_bytes_from_catalog() -> None:
    """Catalog value (KB) is converted to bytes."""
    node = ActivityNode(node_id="n", node_type="script", parameters={})
    result = resolve_max_output_bytes(node, {"workflow_engine.script_max_output_kb": 512})
    assert result == 512 * 1024


def test_resolve_max_output_bytes_fallback() -> None:
    """Default is used when no catalog value is present."""
    node = ActivityNode(node_id="n", node_type="script", parameters={})
    result = resolve_max_output_bytes(node, {})
    assert result == DEFAULT_MAX_OUTPUT_BYTES


def test_resolve_max_output_bytes_non_script_node() -> None:
    """Non-script nodes fall back to default (no catalog key mapped)."""
    node = ActivityNode(node_id="n", node_type="http_request", parameters={})
    result = resolve_max_output_bytes(node, {"workflow_engine.script_max_output_kb": 512})
    assert result == DEFAULT_MAX_OUTPUT_BYTES


# --- expected_duration model validation tests (AAP-92824) ---


def test_expected_duration_accepts_valid_value() -> None:
    """expected_duration accepts positive integers."""
    settings = NodeSettingsNoRetry(expected_duration=60)
    assert settings.expected_duration == 60


def test_expected_duration_defaults_to_none() -> None:
    """expected_duration defaults to None when not provided."""
    settings = NodeSettingsNoRetry()
    assert settings.expected_duration is None


def test_expected_duration_rejects_zero() -> None:
    """expected_duration must be >= 1."""
    with pytest.raises(ValidationError):
        NodeSettingsNoRetry(expected_duration=0)


def test_expected_duration_rejects_negative() -> None:
    """expected_duration must be >= 1."""
    with pytest.raises(ValidationError):
        NodeSettingsNoRetry(expected_duration=-5)


# --- resolve_expected_duration tests (AAP-92824) ---


def test_resolve_expected_duration_node_override() -> None:
    """Per-node expected_duration takes precedence over catalog default."""
    node = ActivityNode(
        node_id="n",
        node_type="script",
        parameters={},
        settings=NodeSettingsNoRetry(expected_duration=60),
    )
    result = resolve_expected_duration(node, {"workflow_engine.script_expected_duration_seconds": 120})
    assert result == 60


def test_resolve_expected_duration_catalog_fallback() -> None:
    """Catalog default is used when node setting is not set."""
    node = ActivityNode(node_id="n", node_type="script", parameters={})
    result = resolve_expected_duration(node, {"workflow_engine.script_expected_duration_seconds": 120})
    assert result == 120


def test_resolve_expected_duration_none_when_unset() -> None:
    """Returns None when neither node nor catalog sets expected_duration."""
    node = ActivityNode(node_id="n", node_type="script", parameters={})
    result = resolve_expected_duration(node, {})
    assert result is None


def test_resolve_expected_duration_none_for_control_node() -> None:
    """Control nodes (no NodeSettingsNoRetry) always return None."""
    node = ActivityNode(
        node_id="n",
        node_type="converge",
        parameters={},
        settings=NodeSettingsCof(),
    )
    result = resolve_expected_duration(node, {"workflow_engine.script_expected_duration_seconds": 120})
    assert result is None


def test_resolve_expected_duration_different_node_types() -> None:
    """Each executor node type resolves from its own catalog key."""
    for node_type, key in [
        ("http_request", "workflow_engine.http_request_expected_duration_seconds"),
        ("aap_job_template", "workflow_engine.aap_expected_duration_seconds"),
        ("agentic", "workflow_engine.agentic_expected_duration_seconds"),
    ]:
        node = ActivityNode(node_id="n", node_type=node_type, parameters={})
        result = resolve_expected_duration(node, {key: 90})
        assert result == 90, f"Failed for {node_type}"
