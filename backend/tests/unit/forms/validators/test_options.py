"""Unit tests for dynamic option resolution."""

from typing import Any

import pytest

from syntara.core.constants import FieldLimits
from syntara.forms.validators.options import resolve_dynamic_options


class TestResolveDynamicOptions:
    """resolve_dynamic_options converts upstream output into static options."""

    def test_scalars_become_options(self) -> None:
        """Each scalar becomes both label and value."""
        options = resolve_dynamic_options(["a", "b"], "region")

        assert options.source == "static"
        assert [(opt.display_label, opt.value) for opt in options.values] == [("a", "a"), ("b", "b")]

    def test_mixed_scalar_types(self) -> None:
        """str/int/float/bool are all supported, each preserving its own type."""
        options = resolve_dynamic_options(["a", 1, 2.5, False], "region")

        assert [opt.value for opt in options.values] == ["a", 1, 2.5, False]
        assert [type(opt.value) for opt in options.values] == [str, int, float, bool]
        assert [opt.display_label for opt in options.values] == ["a", "1", "2.5", "False"]

    def test_bool_collides_with_equal_int(self) -> None:
        """De-duplication compares by equality, so True is dropped after 1 (and vice versa).

        Documents current behavior: `1 == True` in Python, so the second value is
        treated as a duplicate rather than a distinct option.
        """
        options = resolve_dynamic_options([1, True, 0, False], "region")

        assert [opt.value for opt in options.values] == [1, 0]

    def test_duplicates_removed_first_wins(self) -> None:
        """Duplicate values are dropped, preserving first-occurrence order."""
        options = resolve_dynamic_options(["b", "a", "b"], "region")

        assert [opt.value for opt in options.values] == ["b", "a"]

    def test_max_options_allowed(self) -> None:
        """A list exactly at the cap is accepted."""
        options = resolve_dynamic_options(list(range(FieldLimits.FORM_OPTIONS_MAX_LENGTH)), "region")

        assert len(options.values) == FieldLimits.FORM_OPTIONS_MAX_LENGTH

    @pytest.mark.parametrize("resolved", ["abc", {"a": 1}, None, 42])
    def test_non_list_rejected(self, resolved: Any) -> None:  # noqa: ANN401
        """A non-list resolution is a bug in the upstream node, not a scalar to wrap."""
        with pytest.raises(TypeError, match="region"):
            resolve_dynamic_options(resolved, "region")

    def test_empty_list_rejected(self) -> None:
        """An empty option list is rejected."""
        with pytest.raises(ValueError, match="empty list"):
            resolve_dynamic_options([], "region")

    def test_over_cap_rejected(self) -> None:
        """Exceeding the option cap is rejected."""
        with pytest.raises(ValueError, match=str(FieldLimits.FORM_OPTIONS_MAX_LENGTH)):
            resolve_dynamic_options(list(range(FieldLimits.FORM_OPTIONS_MAX_LENGTH + 1)), "region")

    @pytest.mark.parametrize(
        ("resolved", "expected_type"),
        [
            ([{"a": 1}], "dict"),
            ([["nested"]], "list"),
            (["ok", None], "NoneType"),
        ],
    )
    def test_non_scalar_elements_rejected(self, resolved: list[Any], expected_type: str) -> None:
        """Non-scalar elements are rejected and named in the message."""
        with pytest.raises(TypeError, match=expected_type):
            resolve_dynamic_options(resolved, "region")

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_numbers_rejected(self, bad: float) -> None:
        """NaN/Infinity are rejected, matching _coerce_number's rule for submitted values.

        They are not valid JSON, and nan != nan would silently defeat de-duplication.
        """
        with pytest.raises(ValueError, match="non-finite"):
            resolve_dynamic_options(["ok", bad], "region")
