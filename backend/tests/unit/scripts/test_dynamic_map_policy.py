"""Tests for dynamic_map_policy and check_dynamic_map_field_registry."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
TOOLS_CI = ROOT / "tools" / "ci"
SCRIPTS_OPENAPI = ROOT / "scripts" / "openapi"
sys.path.insert(0, str(SCRIPTS_OPENAPI))

from dynamic_map_policy import (  # noqa: E402
    DYNAMIC_MAP_FIELD_NAMES,
    collect_policy_registry_field_names,
)

spec = importlib.util.spec_from_file_location(
    "check_dynamic_map_field_registry",
    TOOLS_CI / "check_dynamic_map_field_registry.py",
)
registry = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(registry)


class TestCollectPolicyRegistryFieldNames:
    """Tests for collect_policy_registry_field_names()."""

    def test_labels_and_data_suffix_fields_are_registry_candidates(self):
        spec_data = yaml.safe_load(
            textwrap.dedent("""\
                components:
                  schemas:
                    Example:
                      type: object
                      properties:
                        labels:
                          type: object
                          additionalProperties:
                            type: string
                        input_data:
                          type: object
                          additionalProperties: true
            """)
        )
        assert collect_policy_registry_field_names(spec_data) == {"labels", "input_data"}

    def test_excluded_signal_data_is_not_a_registry_candidate(self):
        spec_data = yaml.safe_load(
            textwrap.dedent("""\
                components:
                  schemas:
                    Example:
                      type: object
                      properties:
                        signal_data:
                          type: object
                          additionalProperties: true
            """)
        )
        assert collect_policy_registry_field_names(spec_data) == set()


class TestFindUnregisteredFields:
    """Tests for unregistered dynamic-map field detection."""

    def test_detects_unregistered_data_suffix_field(self):
        spec_data = yaml.safe_load(
            textwrap.dedent("""\
                components:
                  schemas:
                    Example:
                      type: object
                      properties:
                        custom_data:
                          type: object
                          additionalProperties: true
            """)
        )
        discovered = {"custom_data": {"src/syntara/schemas/example/openapi.yaml"}}
        unregistered = set(discovered) - set(DYNAMIC_MAP_FIELD_NAMES)
        assert "custom_data" in unregistered
        assert collect_policy_registry_field_names(spec_data) == {"custom_data"}
