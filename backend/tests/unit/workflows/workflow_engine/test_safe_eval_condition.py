"""Unit tests for safe_eval_condition and supporting helpers.

Tests that the safe expression evaluator correctly handles boolean literals,
string/numeric comparisons, and rejects malicious or unsupported expressions.
"""

import pytest

from syntara.workflows.workflow_engine.expression_resolver import safe_eval_condition


class TestBooleanLiterals:
    """safe_eval_condition handles boolean literal expressions."""

    def test_true_literal(self) -> None:
        assert safe_eval_condition("True") is True

    def test_false_literal(self) -> None:
        assert safe_eval_condition("False") is False

    def test_true_with_whitespace(self) -> None:
        assert safe_eval_condition("  True  ") is True

    def test_false_with_whitespace(self) -> None:
        assert safe_eval_condition("  False  ") is False


class TestNumericComparisons:
    """safe_eval_condition handles numeric comparisons."""

    def test_greater_than_true(self) -> None:
        assert safe_eval_condition("5 > 3") is True

    def test_greater_than_false(self) -> None:
        assert safe_eval_condition("3 > 5") is False

    def test_less_than_true(self) -> None:
        assert safe_eval_condition("3 < 5") is True

    def test_less_than_false(self) -> None:
        assert safe_eval_condition("5 < 3") is False

    def test_greater_equal_true_when_greater(self) -> None:
        assert safe_eval_condition("10 >= 5") is True

    def test_greater_equal_true_when_equal(self) -> None:
        assert safe_eval_condition("5 >= 5") is True

    def test_greater_equal_false(self) -> None:
        assert safe_eval_condition("3 >= 5") is False

    def test_less_equal_true_when_less(self) -> None:
        assert safe_eval_condition("3 <= 5") is True

    def test_less_equal_true_when_equal(self) -> None:
        assert safe_eval_condition("5 <= 5") is True

    def test_less_equal_false(self) -> None:
        assert safe_eval_condition("10 <= 5") is False

    def test_equal_integers(self) -> None:
        assert safe_eval_condition("5 == 5") is True

    def test_not_equal_integers(self) -> None:
        assert safe_eval_condition("5 != 3") is True

    def test_not_equal_integers_false(self) -> None:
        assert safe_eval_condition("5 != 5") is False

    def test_negative_number(self) -> None:
        assert safe_eval_condition("-1 < 0") is True

    def test_float_comparison(self) -> None:
        assert safe_eval_condition("3.14 > 2.71") is True


class TestStringComparisons:
    """safe_eval_condition handles string comparisons."""

    def test_string_equality_true(self) -> None:
        assert safe_eval_condition('"dev" == "dev"') is True

    def test_string_equality_false(self) -> None:
        assert safe_eval_condition('"dev" == "prod"') is False

    def test_string_not_equal_true(self) -> None:
        assert safe_eval_condition('"dev" != "prod"') is True

    def test_string_not_equal_false(self) -> None:
        assert safe_eval_condition('"dev" != "dev"') is False

    def test_single_quoted_strings(self) -> None:
        assert safe_eval_condition("'active' == 'active'") is True

    def test_status_check_pattern(self) -> None:
        """Common workflow pattern: status == "active"."""
        assert safe_eval_condition('"active" == "active"') is True


class TestChainedComparisons:
    """safe_eval_condition handles chained comparison expressions."""

    def test_chained_comparison_true(self) -> None:
        assert safe_eval_condition("1 < 2 < 3") is True

    def test_chained_comparison_false(self) -> None:
        assert safe_eval_condition("1 < 2 > 3") is False


class TestUnaryOperators:
    """safe_eval_condition handles unary operators."""

    def test_not_true(self) -> None:
        assert safe_eval_condition("not True") is False

    def test_not_false(self) -> None:
        assert safe_eval_condition("not False") is True

    def test_unary_minus(self) -> None:
        assert safe_eval_condition("-5 < 0") is True


class TestNonNumericOrderingComparisonsRejected:
    """Ordering comparisons on non-numeric strings raise ValueError."""

    def test_string_greater_than_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot compare non-numeric"):
            safe_eval_condition('"apple" > "banana"')

    def test_string_less_than_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot compare non-numeric"):
            safe_eval_condition('"apple" < "banana"')


class TestMaliciousExpressions:
    """safe_eval_condition rejects dangerous expressions that eval() would execute."""

    def test_import_system_call_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression type"):
            safe_eval_condition("__import__('os').system('echo pwned')")

    def test_dunder_import_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression type"):
            safe_eval_condition("__import__('subprocess')")

    def test_attribute_access_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression type"):
            safe_eval_condition("obj.method()")

    def test_function_call_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression type"):
            safe_eval_condition("print('hello')")

    def test_lambda_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression type"):
            safe_eval_condition("lambda: None")

    def test_list_comprehension_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression type"):
            safe_eval_condition("[x for x in range(10)]")

    def test_exec_rejected(self) -> None:
        """exec() is a statement in Python 3, so ast.parse in eval mode raises SyntaxError -> ValueError."""
        with pytest.raises(ValueError):
            safe_eval_condition("exec('import os')")

    def test_nested_call_in_comparison_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression type"):
            safe_eval_condition("len('abc') == 3")

    def test_walrus_operator_rejected(self) -> None:
        with pytest.raises(ValueError):
            safe_eval_condition("(x := 5) == 5")

    def test_binary_arithmetic_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression type"):
            safe_eval_condition("2 + 2")


class TestEdgeCases:
    """Edge cases and error handling for safe_eval_condition."""

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty condition expression"):
            safe_eval_condition("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty condition expression"):
            safe_eval_condition("   ")

    def test_invalid_syntax_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid condition expression"):
            safe_eval_condition("== ==")

    def test_none_literal_is_falsy(self) -> None:
        assert safe_eval_condition("None") is False

    def test_zero_is_falsy(self) -> None:
        assert safe_eval_condition("0") is False

    def test_nonzero_is_truthy(self) -> None:
        assert safe_eval_condition("1") is True

    def test_nonempty_string_is_truthy(self) -> None:
        assert safe_eval_condition('"hello"') is True

    def test_empty_string_literal_is_falsy(self) -> None:
        assert safe_eval_condition('""') is False

    def test_unsupported_comparison_operator_in_rejected(self) -> None:
        """The 'in' operator is not in the allowed set."""
        with pytest.raises(ValueError, match="Unsupported comparison operator"):
            safe_eval_condition('"a" in "abc"')

    def test_unsupported_comparison_operator_is_rejected(self) -> None:
        """The 'is' operator is not in the allowed set."""
        with pytest.raises(ValueError, match="Unsupported comparison operator"):
            safe_eval_condition("True is True")
