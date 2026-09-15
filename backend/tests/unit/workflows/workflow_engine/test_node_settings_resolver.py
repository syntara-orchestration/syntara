"""Tests for node_settings_resolver pure functions."""

import pytest

from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.workflows.workflow_engine.constants import DEFAULT_MAX_OUTPUT_BYTES
from syntara.workflows.workflow_engine.graph import ActivityNode
from syntara.workflows.workflow_engine.node_settings_resolver import resolve_max_output_bytes, resolve_retry_policy


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


def test_resolve_response_window_from_node() -> None:
    """Node parameter value is used when present."""
    from syntara.workflows.workflow_engine.node_settings_resolver import resolve_response_window

    node = ActivityNode(node_id="n", node_type="form_prompt", parameters={"response_window": 7200})
    result = resolve_response_window(node, {})
    assert result == 7200


def test_resolve_response_window_from_catalog() -> None:
    """Catalog value is used when node value is absent."""
    from syntara.workflows.workflow_engine.node_settings_resolver import resolve_response_window

    node = ActivityNode(node_id="n", node_type="form_prompt", parameters={})
    result = resolve_response_window(node, {"workflow_engine.form_prompt_response_window_seconds": 3600})
    assert result == 3600


def test_resolve_response_window_fallback() -> None:
    """Falls back to 86400 when no catalog value."""
    from syntara.workflows.workflow_engine.node_settings_resolver import resolve_response_window

    node = ActivityNode(node_id="n", node_type="form_prompt", parameters={})
    result = resolve_response_window(node, {})
    assert result == 86400


def test_resolve_response_window_non_integer_raises() -> None:
    """Non-integer response_window raises ConfigError."""
    from temporalio.exceptions import ApplicationError

    from syntara.workflows.workflow_engine.node_settings_resolver import resolve_response_window

    node = ActivityNode(node_id="n", node_type="form_prompt", parameters={"response_window": "not_an_int"})
    with pytest.raises(ApplicationError, match="ConfigError"):
        resolve_response_window(node, {})
