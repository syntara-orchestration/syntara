"""Tests for context_manager settings in the SETTINGS_CATALOG.

Verifies that all context_manager settings are correctly defined in the
catalog as SettingDefinition entries under the context_manager category.

Key convention: context_manager.{field} SettingCategory.CONTEXT_MANAGER.

Validation schema mapping from Pydantic validators:
  ge=X  → {"min": X}
  le=X  → {"max": X}
  ge+le → {"min": X, "max": Y}
"""

from __future__ import annotations

import pytest

from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.settings.models.runtime_setting import SettingCategory, SettingValueType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CATALOG_BY_KEY = {d.key: d for d in SETTINGS_CATALOG}

_EXPECTED_KEYS: list[str] = [
    "context_manager.required_grounding_score",
    "context_manager.minimum_grounding_score",
    "context_manager.max_total_tokens",
    "context_manager.max_context_tokens",
    "context_manager.max_system_tokens",
    "context_manager.max_user_tokens",
    "context_manager.default_k",
    "context_manager.enable_hybrid_search",
    "context_manager.semantic_weight",
    "context_manager.lexical_weight",
    "context_manager.compression_mode",
    "context_manager.max_snippets_per_doc",
    "context_manager.snippet_min_length",
    "context_manager.snippet_max_length",
    "context_manager.enforce_hierarchy",
    "context_manager.priority_order",
    "context_manager.include_citations",
    "context_manager.request_timeout_seconds",
    "context_manager.max_concurrent_requests",
    "context_manager.compression_loop",
    "context_manager.compression_temperature",
    "context_manager.compression_max_tokens",
    "context_manager.output_token_reserve",
    "context_manager.tokenizer_safety_margin",
]


# ---------------------------------------------------------------------------
# Category enum
# ---------------------------------------------------------------------------


def test_context_manager_category_exists() -> None:
    """SettingCategory must define a CONTEXT_MANAGER member with value 'context_manager'."""
    assert hasattr(SettingCategory, "CONTEXT_MANAGER"), "SettingCategory.CONTEXT_MANAGER not defined"
    assert SettingCategory.CONTEXT_MANAGER.value == "context_manager"


# ---------------------------------------------------------------------------
# Catalog presence
# ---------------------------------------------------------------------------


def test_all_context_manager_keys_in_catalog() -> None:
    """All context_manager keys must be present in SETTINGS_CATALOG."""
    catalog_keys = {d.key for d in SETTINGS_CATALOG}
    missing = [k for k in _EXPECTED_KEYS if k not in catalog_keys]
    assert not missing, f"Keys missing from catalog: {missing}"


def test_no_extra_context_manager_keys_in_catalog() -> None:
    """Only the expected keys are in the catalog under CONTEXT_MANAGER (no typos)."""
    catalog_cm_keys = {d.key for d in SETTINGS_CATALOG if d.category == SettingCategory.CONTEXT_MANAGER}
    expected = set(_EXPECTED_KEYS)
    extra = catalog_cm_keys - expected
    assert not extra, f"Unexpected context_manager keys in catalog: {extra}"


# ---------------------------------------------------------------------------
# Category assignment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", _EXPECTED_KEYS)
def test_context_manager_keys_have_correct_category(key: str) -> None:
    """Every context_manager.* setting must use SettingCategory.CONTEXT_MANAGER."""
    defn = _CATALOG_BY_KEY[key]
    assert defn.category.value == "context_manager", (
        f"{key}: expected category value 'context_manager', got {defn.category.value!r}"
    )


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected_type"),
    [
        ("context_manager.required_grounding_score", SettingValueType.FLOAT),
        ("context_manager.minimum_grounding_score", SettingValueType.FLOAT),
        ("context_manager.max_total_tokens", SettingValueType.INTEGER),
        ("context_manager.max_context_tokens", SettingValueType.INTEGER),
        ("context_manager.max_system_tokens", SettingValueType.INTEGER),
        ("context_manager.max_user_tokens", SettingValueType.INTEGER),
        ("context_manager.default_k", SettingValueType.INTEGER),
        ("context_manager.enable_hybrid_search", SettingValueType.BOOLEAN),
        ("context_manager.semantic_weight", SettingValueType.FLOAT),
        ("context_manager.lexical_weight", SettingValueType.FLOAT),
        ("context_manager.compression_mode", SettingValueType.STRING),
        ("context_manager.max_snippets_per_doc", SettingValueType.INTEGER),
        ("context_manager.snippet_min_length", SettingValueType.INTEGER),
        ("context_manager.snippet_max_length", SettingValueType.INTEGER),
        ("context_manager.enforce_hierarchy", SettingValueType.BOOLEAN),
        ("context_manager.priority_order", SettingValueType.JSON),
        ("context_manager.include_citations", SettingValueType.BOOLEAN),
        ("context_manager.request_timeout_seconds", SettingValueType.INTEGER),
        ("context_manager.max_concurrent_requests", SettingValueType.INTEGER),
        ("context_manager.compression_loop", SettingValueType.INTEGER),
        ("context_manager.compression_temperature", SettingValueType.FLOAT),
        ("context_manager.compression_max_tokens", SettingValueType.INTEGER),
        ("context_manager.output_token_reserve", SettingValueType.INTEGER),
        ("context_manager.tokenizer_safety_margin", SettingValueType.FLOAT),
    ],
)
def test_context_manager_value_types(key: str, expected_type: SettingValueType) -> None:
    """Each context_manager setting must have the correct SettingValueType."""
    defn = _CATALOG_BY_KEY[key]
    assert defn.value_type == expected_type, f"{key}: expected {expected_type}, got {defn.value_type}"


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected_default"),
    [
        ("context_manager.required_grounding_score", 0.7),
        ("context_manager.minimum_grounding_score", 0.5),
        ("context_manager.max_total_tokens", 4000),
        ("context_manager.max_context_tokens", 3000),
        ("context_manager.max_system_tokens", 500),
        ("context_manager.max_user_tokens", 500),
        ("context_manager.default_k", 10),
        ("context_manager.enable_hybrid_search", True),
        ("context_manager.semantic_weight", 0.7),
        ("context_manager.lexical_weight", 0.3),
        ("context_manager.compression_mode", "extractive"),
        ("context_manager.max_snippets_per_doc", 3),
        ("context_manager.snippet_min_length", 100),
        ("context_manager.snippet_max_length", 500),
        ("context_manager.enforce_hierarchy", True),
        ("context_manager.priority_order", ["system", "context", "user"]),
        ("context_manager.include_citations", True),
        ("context_manager.request_timeout_seconds", 30),
        ("context_manager.max_concurrent_requests", 5),
        ("context_manager.compression_loop", 3),
        ("context_manager.compression_temperature", 0.3),
        ("context_manager.compression_max_tokens", 2000),
        ("context_manager.output_token_reserve", 4096),
        ("context_manager.tokenizer_safety_margin", 0.90),
    ],
)
def test_context_manager_default_values(key: str, expected_default: object) -> None:
    """Each context_manager setting must carry the correct default_value."""
    defn = _CATALOG_BY_KEY[key]
    assert defn.default_value == expected_default, (
        f"{key}: expected default {expected_default!r}, got {defn.default_value!r}"
    )


# ---------------------------------------------------------------------------
# Validation schemas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected_schema"),
    [
        ("context_manager.required_grounding_score", {"min": 0.0, "max": 1.0}),
        ("context_manager.minimum_grounding_score", {"min": 0.0, "max": 1.0}),
        ("context_manager.max_total_tokens", {"min": 1}),
        ("context_manager.max_context_tokens", {"min": 1}),
        ("context_manager.max_system_tokens", {"min": 1}),
        ("context_manager.max_user_tokens", {"min": 1}),
        ("context_manager.default_k", {"min": 1}),
        ("context_manager.enable_hybrid_search", None),
        ("context_manager.semantic_weight", {"min": 0.0, "max": 1.0}),
        ("context_manager.lexical_weight", {"min": 0.0, "max": 1.0}),
        ("context_manager.compression_mode", {"allowed_values": ["extractive", "abstractive"]}),
        ("context_manager.max_snippets_per_doc", {"min": 1}),
        ("context_manager.snippet_min_length", {"min": 1}),
        ("context_manager.snippet_max_length", {"min": 1}),
        ("context_manager.enforce_hierarchy", None),
        ("context_manager.priority_order", None),
        ("context_manager.include_citations", None),
        ("context_manager.request_timeout_seconds", {"min": 1}),
        ("context_manager.max_concurrent_requests", {"min": 1}),
        ("context_manager.compression_loop", {"min": 0}),
        ("context_manager.compression_temperature", {"min": 0.0, "max": 1.0}),
        ("context_manager.compression_max_tokens", {"min": 1}),
        ("context_manager.output_token_reserve", {"min": 256}),
        ("context_manager.tokenizer_safety_margin", {"min": 0.5, "max": 1.0}),
    ],
)
def test_context_manager_validation_schemas(key: str, expected_schema: dict[str, int | float] | None) -> None:
    """Validation schemas must reflect expected min/max constraints."""
    defn = _CATALOG_BY_KEY[key]
    assert defn.validation_schema == expected_schema, (
        f"{key}: expected schema {expected_schema!r}, got {defn.validation_schema!r}"
    )
