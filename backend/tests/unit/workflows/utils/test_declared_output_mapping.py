"""Tests for SubWorkflow Trigger declared output mapping at runtime."""

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.utils.output_mapping import DeclaredOutputContractError, apply_declared_output_mapping


def _resolver() -> NamespaceResolver:
    resolver = NamespaceResolver()
    resolver.set_namespace("deploy", {"url": "https://example.test/app", "id": 42})
    return resolver


def test_maps_declared_outputs_to_nested_paths() -> None:
    schema = {
        "type": "object",
        "properties": {
            "release": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            }
        },
        "required": ["release"],
    }

    outputs = apply_declared_output_mapping(_resolver(), schema, {"release.url": "${deploy.url}"})

    assert outputs == {"release": {"url": "https://example.test/app"}}


def test_omits_unavailable_optional_output() -> None:
    schema = {"type": "object", "properties": {"url": {"type": "string"}}}

    outputs = apply_declared_output_mapping(_resolver(), schema, {"url": "${missing.url}"})

    assert outputs == {}


def test_missing_required_output_fails_contract() -> None:
    schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    with pytest.raises(DeclaredOutputContractError, match="'url'"):
        apply_declared_output_mapping(_resolver(), schema, {"url": "${missing.url}"})


def test_output_type_mismatch_fails_contract() -> None:
    schema = {"type": "object", "properties": {"release_id": {"type": "string"}}}

    with pytest.raises(DeclaredOutputContractError, match="release_id"):
        apply_declared_output_mapping(_resolver(), schema, {"release_id": "${deploy.id}"})


def test_conflicting_nested_paths_fail_contract() -> None:
    schema = {
        "type": "object",
        "properties": {"release": {"type": "object", "properties": {"url": {"type": "string"}}}},
    }

    with pytest.raises(DeclaredOutputContractError, match="Conflicting"):
        apply_declared_output_mapping(
            _resolver(),
            schema,
            {"release": "${deploy.url}", "release.url": "${deploy.url}"},
        )
