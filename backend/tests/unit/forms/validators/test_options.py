"""Unit tests for dynamic option and form-definition resolution."""

import copy
import json
from typing import Any

import pytest

from syntara.core.constants import FieldLimits
from syntara.core.exceptions import SafeValueError
from syntara.forms.validators.options import resolve_dynamic_option_values, resolve_dynamic_options


class TestResolveDynamicOptionValues:
    """Record upstream values retain type and stable order."""

    def test_source_is_dynamic_resolved(self) -> None:
        options = resolve_dynamic_option_values(
            [{"display_label": "a", "value": "a"}, {"display_label": "b", "value": "b"}], "region"
        )

        assert options.source == "dynamic_resolved"
        assert [(option.display_label, option.value) for option in options.values] == [("a", "a"), ("b", "b")]

    def test_duplicates_removed_first_wins(self) -> None:
        options = resolve_dynamic_option_values(
            [
                {"display_label": "First B", "value": "b"},
                {"display_label": "A", "value": "a"},
                {"display_label": "Second B", "value": "b"},
            ],
            "region",
        )

        assert [(option.display_label, option.value) for option in options.values] == [("First B", "b"), ("A", "a")]

    def test_equal_typed_values_are_deduplicated(self) -> None:
        """Python set equality collapses 1/True and 0/False, keeping the first."""
        options = resolve_dynamic_option_values(
            [
                {"display_label": "One", "value": 1},
                {"display_label": "True", "value": True},
                {"display_label": "Zero", "value": 0},
                {"display_label": "False", "value": False},
            ],
            "region",
        )

        assert [option.value for option in options.values] == [1, 0]

    def test_max_options_allowed(self) -> None:
        records = [
            {"display_label": str(index), "value": index} for index in range(FieldLimits.FORM_OPTIONS_MAX_LENGTH)
        ]
        options = resolve_dynamic_option_values(records, "region")

        assert len(options.values) == FieldLimits.FORM_OPTIONS_MAX_LENGTH

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_rejected(self, bad: float) -> None:
        with pytest.raises(ValueError, match="NaN and Infinity"):
            resolve_dynamic_option_values([{"display_label": "bad", "value": bad}], "region")

    def test_over_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match=str(FieldLimits.FORM_OPTIONS_MAX_LENGTH)):
            resolve_dynamic_option_values(
                [
                    {"display_label": str(index), "value": index}
                    for index in range(FieldLimits.FORM_OPTIONS_MAX_LENGTH + 1)
                ],
                "region",
            )

    @pytest.mark.parametrize("resolved", ["abc", {"a": 1}, None, 42])
    def test_non_list_rejected(self, resolved: Any) -> None:  # noqa: ANN401
        with pytest.raises(TypeError, match="region") as exc_info:
            resolve_dynamic_option_values(resolved, "region")

        assert "Do not coerce scalars into single-item lists" in str(exc_info.value)

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty list"):
            resolve_dynamic_option_values([], "region")

    @pytest.mark.parametrize("item", ["a", 1, 1.5, False, ["a"]])
    def test_non_record_item_rejected_with_index(self, item: Any) -> None:  # noqa: ANN401
        with pytest.raises(TypeError, match=r"index 0.*object"):
            resolve_dynamic_option_values([item], "region")

    def test_none_element_rejected_with_index(self) -> None:
        with pytest.raises(TypeError, match=r"index 1.*NoneType"):
            resolve_dynamic_option_values([{"display_label": "a", "value": "a"}, None], "region")

    def test_error_never_contains_raw_value(self) -> None:
        with pytest.raises(TypeError) as exc_info:
            resolve_dynamic_option_values([{"display_label": "ok", "value": {"password": "hunter2"}}], "region")

        assert "hunter2" not in str(exc_info.value)


class TestResolveDynamicOptionsRecords:
    """Record upstream values honor configured keys and are validated safely."""

    def test_default_keys(self) -> None:
        options = resolve_dynamic_option_values([{"display_label": "US East", "value": "us-east-1"}], "region")

        assert [(option.display_label, option.value) for option in options.values] == [("US East", "us-east-1")]

    def test_configured_keys(self) -> None:
        options = resolve_dynamic_option_values(
            [{"name": "US East", "id": "us-east-1"}], "region", label_key="name", value_key="id"
        )

        assert [(option.display_label, option.value) for option in options.values] == [("US East", "us-east-1")]

    def test_value_type_preserved_in_records(self) -> None:
        options = resolve_dynamic_option_values([{"name": "One", "id": 1}], "region", label_key="name", value_key="id")

        assert options.values[0].value == 1
        assert type(options.values[0].value) is int

    def test_missing_label_key_rejected(self) -> None:
        with pytest.raises(TypeError, match=r"region.*index 0.*label key 'name'"):
            resolve_dynamic_option_values([{"id": "us"}], "region", label_key="name", value_key="id")

    def test_empty_label_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"region.*index 0.*empty label"):
            resolve_dynamic_option_values([{"display_label": "", "value": ""}], "region")

    def test_non_string_label_rejected(self) -> None:
        with pytest.raises(TypeError, match=r"region.*index 0.*non-string label.*int"):
            resolve_dynamic_option_values([{"display_label": 123, "value": "x"}], "region")

    def test_label_over_max_length_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"region.*index 0.*longer than 200"):
            resolve_dynamic_option_values([{"display_label": "x" * 201, "value": "x"}], "region")

    def test_missing_value_key_rejected(self) -> None:
        with pytest.raises(TypeError, match=r"region.*index 0.*value key 'value'"):
            resolve_dynamic_option_values([{"display_label": "US"}], "region")

    def test_nested_value_rejected(self) -> None:
        with pytest.raises(TypeError, match=r"region.*index 0.*key 'value'.*dict"):
            resolve_dynamic_option_values([{"display_label": "US", "value": {"a": 1}}], "region")

    def test_extra_record_keys_ignored(self) -> None:
        options = resolve_dynamic_option_values(
            [{"display_label": "US", "value": "us", "metadata": {"x": 1}}], "region"
        )

        assert [(option.display_label, option.value) for option in options.values] == [("US", "us")]

    def test_record_dedup_by_value_first_wins(self) -> None:
        options = resolve_dynamic_option_values(
            [
                {"display_label": "First", "value": "us"},
                {"display_label": "Second", "value": "us"},
            ],
            "region",
        )

        assert [(option.display_label, option.value) for option in options.values] == [("First", "us")]

    def test_non_record_item_rejected(self) -> None:
        with pytest.raises(TypeError, match=r"region.*index 1.*object"):
            resolve_dynamic_option_values([{"display_label": "a", "value": "a"}, "b"], "region")

    def test_record_list_over_cap_rejected(self) -> None:
        records = [
            {"display_label": str(index), "value": index} for index in range(FieldLimits.FORM_OPTIONS_MAX_LENGTH + 1)
        ]

        with pytest.raises(ValueError, match=str(FieldLimits.FORM_OPTIONS_MAX_LENGTH)):
            resolve_dynamic_option_values(records, "region")


class TestResolveDynamicOptions:
    """The workflow boundary builds immutable JSON-safe option snapshots."""

    @staticmethod
    def _field(field_type: str, value_name: str, expression: Any, **option_keys: str) -> dict[str, Any]:  # noqa: ANN401
        return {
            "type": field_type,
            "value_name": value_name,
            "label": value_name.title(),
            "options": {"source": "dynamic", "expression": expression, **option_keys},
        }

    def test_dropdown_dynamic_becomes_dynamic_resolved(self) -> None:
        definition = {
            "fields": [
                self._field(
                    "dropdown",
                    "region",
                    [{"display_label": "US", "value": "us"}, {"display_label": "EU", "value": "eu"}],
                )
            ]
        }

        result = resolve_dynamic_options(definition)

        assert result["fields"][0]["options"] == {
            "source": "dynamic_resolved",
            "values": [
                {"display_label": "US", "value": "us"},
                {"display_label": "EU", "value": "eu"},
            ],
        }

    def test_multi_select_dynamic_becomes_dynamic_resolved(self) -> None:
        definition = {
            "fields": [
                self._field(
                    "multi_select",
                    "regions",
                    [{"display_label": "US", "value": "us"}, {"display_label": "EU", "value": "eu"}],
                )
            ]
        }

        result = resolve_dynamic_options(definition)

        assert result["fields"][0]["options"]["source"] == "dynamic_resolved"
        assert len(result["fields"][0]["options"]["values"]) == 2

    def test_static_field_untouched(self) -> None:
        field = {
            "type": "dropdown",
            "value_name": "region",
            "label": "Region",
            "options": {"source": "static", "values": [{"display_label": "US", "value": "us"}]},
        }

        result = resolve_dynamic_options({"fields": [field]})

        assert result["fields"][0] == field

    def test_non_option_fields_untouched(self) -> None:
        fields = [
            {"type": "text", "value_name": "name", "label": "Name", "default": "A"},
            {"type": "number", "value_name": "count", "label": "Count", "default": 2},
            {"type": "checkbox", "value_name": "accepted", "label": "Accepted"},
        ]

        result = resolve_dynamic_options({"fields": fields})

        assert result["fields"] == fields

    def test_multiple_dynamic_fields_resolve_independently(self) -> None:
        result = resolve_dynamic_options(
            {
                "fields": [
                    self._field("dropdown", "region", [{"display_label": "US", "value": "us"}]),
                    self._field(
                        "multi_select",
                        "team",
                        [{"display_label": "One", "value": 1}, {"display_label": "Two", "value": 2}],
                    ),
                ]
            }
        )

        assert result["fields"][0]["options"]["values"][0]["value"] == "us"
        assert [option["value"] for option in result["fields"][1]["options"]["values"]] == [1, 2]

    def test_input_not_mutated(self) -> None:
        definition = {"fields": [self._field("dropdown", "region", [{"display_label": "US", "value": "us"}])]}
        before = copy.deepcopy(definition)

        resolve_dynamic_options(definition)

        assert definition == before

    def test_output_is_json_serializable(self) -> None:
        result = resolve_dynamic_options(
            {
                "fields": [
                    self._field(
                        "dropdown",
                        "region",
                        [{"display_label": "One", "value": 1}, {"display_label": "False", "value": False}],
                    )
                ]
            }
        )

        assert json.loads(json.dumps(result)) == result

    def test_record_keys_are_resolved(self) -> None:
        result = resolve_dynamic_options(
            {
                "fields": [
                    self._field(
                        "dropdown",
                        "region",
                        [{"name": "US", "id": "us"}],
                        label_key="name",
                        value_key="id",
                    )
                ]
            }
        )

        assert result["fields"][0]["options"] == {
            "source": "dynamic_resolved",
            "values": [{"display_label": "US", "value": "us"}],
        }

    def test_field_error_names_the_field_and_hides_upstream_values(self) -> None:
        definition = {
            "fields": [
                self._field("dropdown", "region", [{"display_label": "OK", "value": "ok"}, {"password": "hunter2"}])
            ]
        }

        with pytest.raises(SafeValueError) as exc_info:
            resolve_dynamic_options(definition)

        assert "region" in str(exc_info.value)
        assert "hunter2" not in str(exc_info.value)

    @pytest.mark.parametrize("bad", ["not-a-list", [], [1, 2], [{"display_label": "US", "value": {"secret": "x"}}]])
    def test_raises_safe_value_error(self, bad: Any) -> None:  # noqa: ANN401
        with pytest.raises(SafeValueError):
            resolve_dynamic_options({"fields": [self._field("dropdown", "region", bad)]})

    @pytest.mark.parametrize("definition", [{}, {"fields": "nope"}])
    def test_malformed_definition_passed_through(self, definition: dict[str, Any]) -> None:
        assert resolve_dynamic_options(definition) is definition

    def test_default_not_in_dynamic_resolved_options_rejected(self) -> None:
        definition = {
            "fields": [
                {
                    **self._field(
                        "dropdown",
                        "region",
                        [{"display_label": "US", "value": "us"}, {"display_label": "APAC", "value": "apac"}],
                    ),
                    "default": "emea",
                }
            ]
        }

        with pytest.raises(SafeValueError, match=r"Field 'region'.*default value 'emea'"):
            resolve_dynamic_options(definition)

    def test_typed_default_matches_dynamic_resolved_value(self) -> None:
        definition = {
            "fields": [
                {
                    **self._field(
                        "dropdown",
                        "region",
                        [
                            {"display_label": "One", "value": 1},
                            {"display_label": "Two", "value": 2},
                            {"display_label": "Three", "value": 3},
                        ],
                    ),
                    "default": 2,
                }
            ]
        }

        result = resolve_dynamic_options(definition)

        assert result["fields"][0]["default"] == 2
        assert type(result["fields"][0]["options"]["values"][1]["value"]) is int

    def test_already_dynamic_resolved_options_passed_through(self) -> None:
        field = {
            "type": "dropdown",
            "value_name": "region",
            "label": "Region",
            "options": {"source": "dynamic_resolved", "values": [{"display_label": "US", "value": 1}]},
        }

        result = resolve_dynamic_options({"fields": [field]})

        assert result["fields"][0] == field
