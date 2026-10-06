"""Tests for node_settings_resolver pure functions."""

import pytest

from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.workflows.workflow_engine.constants import DEFAULT_ACTIVITY_TIMEOUT_SECONDS, DEFAULT_MAX_OUTPUT_BYTES
from syntara.workflows.workflow_engine.graph import ActivityNode
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.node_settings_resolver import (
    get_default_timeout,
    resolve_max_output_bytes,
    resolve_retry_policy,
)

_TFE_STANDARD_SAMPLES = (
    NodeType.TFE_CREATE_WORKSPACE,
    NodeType.TFE_ADD_VARIABLE,
    NodeType.TFE_TRIGGER_RUN,
    NodeType.TFE_GET_RUN_STATUS,
    NodeType.TFE_LIST_PROJECTS,
    NodeType.TFE_ASSIGN_TEAM_PERMISSIONS,
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


def test_tfe_standard_timeout_uses_catalog_default() -> None:
    """TFE API steps resolve to workflow_engine.tfe_timeout_seconds, not the 30s fallback."""
    defaults = _catalog_defaults()
    tfe_timeout = defaults["workflow_engine.tfe_timeout_seconds"]
    assert isinstance(tfe_timeout, int)
    expected = tfe_timeout
    assert expected > DEFAULT_ACTIVITY_TIMEOUT_SECONDS
    for node_type in _TFE_STANDARD_SAMPLES:
        assert get_default_timeout(node_type, defaults) == expected


def test_tfe_upload_timeout_uses_long_running_catalog_default() -> None:
    """Configuration uploads use a longer catalog timeout than ordinary TFE steps."""
    defaults = _catalog_defaults()
    upload_value = defaults["workflow_engine.tfe_upload_timeout_seconds"]
    standard_value = defaults["workflow_engine.tfe_timeout_seconds"]
    assert isinstance(upload_value, int)
    assert isinstance(standard_value, int)
    upload = upload_value
    standard = standard_value
    assert upload > standard
    assert get_default_timeout(NodeType.TFE_UPLOAD_CONFIGURATION_VERSION, defaults) == upload


@pytest.mark.parametrize(
    ("node_type", "key"),
    [
        (NodeType.TFE_CREATE_WORKSPACE, "workflow_engine.tfe_timeout_seconds"),
        (NodeType.TFE_UPLOAD_CONFIGURATION_VERSION, "workflow_engine.tfe_upload_timeout_seconds"),
    ],
)
def test_tfe_timeout_respects_runtime_override(node_type: str, key: str) -> None:
    """Operator-configured runtime settings override catalog defaults for TFE."""
    assert get_default_timeout(node_type, {key: 42}) == 42


def test_tfe_timeout_falls_back_without_catalog() -> None:
    """Missing runtime settings still fall back to the global default."""
    assert get_default_timeout(NodeType.TFE_TRIGGER_RUN, {}) == DEFAULT_ACTIVITY_TIMEOUT_SECONDS
