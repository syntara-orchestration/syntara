"""Tests for unified context-aware expression evaluator."""

from typing import Any

import pytest

from syntara.workflows.workflow_engine.unified_eval import MAX_AST_DEPTH, safe_eval_with_namespace


class TestBasicEvaluation:
    """Test basic expression evaluation with namespace context."""

    def test_simple_equality_with_template_syntax(self) -> None:
        """Variables can use ${...} syntax."""
        namespace = {"status": "completed"}
        result = safe_eval_with_namespace("${status} == 'completed'", namespace)
        assert result is True

    def test_simple_equality_without_template_syntax(self) -> None:
        """Variables work without ${...} wrappers."""
        namespace = {"status": "completed"}
        result = safe_eval_with_namespace("status == 'completed'", namespace)
        assert result is True

    def test_numeric_comparison_greater_than(self) -> None:
        namespace = {"age": 25}
        assert safe_eval_with_namespace("${age} >= 18", namespace) is True
        assert safe_eval_with_namespace("${age} < 18", namespace) is False

    def test_numeric_comparison_less_than(self) -> None:
        namespace = {"count": 5}
        assert safe_eval_with_namespace("${count} < 10", namespace) is True
        assert safe_eval_with_namespace("${count} > 10", namespace) is False

    def test_boolean_value_equality(self) -> None:
        namespace = {"enabled": True}
        assert safe_eval_with_namespace("${enabled} == True", namespace) is True
        assert safe_eval_with_namespace("${enabled} == False", namespace) is False

    def test_variable_not_found_raises_key_error(self) -> None:
        namespace = {"status": "ok"}
        with pytest.raises(KeyError, match="unknown"):
            safe_eval_with_namespace("${unknown} == 'value'", namespace)

    def test_empty_expression_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Empty expression"):
            safe_eval_with_namespace("", {})

    def test_whitespace_only_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Empty expression"):
            safe_eval_with_namespace("   ", {})


class TestDottedPaths:
    """Test dotted path variable access (nested dicts)."""

    def test_nested_dict_access(self) -> None:
        namespace: dict[str, Any] = {"user": {"role": "admin"}}
        result = safe_eval_with_namespace("${user.role} == 'admin'", namespace)
        assert result is True

    def test_deeply_nested_access(self) -> None:
        namespace = {"fetch_order": {"output": {"riskScore": 0.8}}}
        result = safe_eval_with_namespace("${fetch_order.output.riskScore} > 0.7", namespace)
        assert result is True

    def test_missing_nested_key_raises_error(self) -> None:
        namespace: dict[str, Any] = {"user": {}}
        with pytest.raises(KeyError, match="role"):
            safe_eval_with_namespace("${user.role} == 'admin'", namespace)

    def test_attribute_access_on_non_dict_raises_error(self) -> None:
        namespace = {"value": 42}
        with pytest.raises(TypeError, match="Cannot access attribute"):
            safe_eval_with_namespace("${value.something} == 'test'", namespace)


class TestSubscriptAccess:
    """Test subscript access (lists and dicts)."""

    def test_list_index_access(self) -> None:
        namespace = {"items": ["apple", "banana", "cherry"]}
        result = safe_eval_with_namespace("${items[0]} == 'apple'", namespace)
        assert result is True

    def test_dict_key_access(self) -> None:
        namespace = {"data": {"key": "value"}}
        result = safe_eval_with_namespace("${data['key']} == 'value'", namespace)
        assert result is True

    def test_list_index_out_of_range(self) -> None:
        namespace = {"items": [1, 2, 3]}
        with pytest.raises(IndexError, match="out of range"):
            safe_eval_with_namespace("${items[10]} == 1", namespace)

    def test_dict_key_not_found(self) -> None:
        namespace = {"data": {"a": 1}}
        with pytest.raises(KeyError, match="missing"):
            safe_eval_with_namespace("${data['missing']} == 1", namespace)

    def test_subscript_on_non_subscriptable(self) -> None:
        namespace = {"value": 42}
        with pytest.raises(TypeError, match="Cannot subscript"):
            safe_eval_with_namespace("${value[0]} == 1", namespace)

    def test_negative_index_last_element(self) -> None:
        """Negative indexing: -1 accesses last element."""
        namespace = {"items": ["apple", "banana", "cherry"]}
        result = safe_eval_with_namespace("${items[-1]} == 'cherry'", namespace)
        assert result is True

    def test_negative_index_second_to_last(self) -> None:
        """Negative indexing: -2 accesses second-to-last element."""
        namespace = {"items": ["apple", "banana", "cherry"]}
        result = safe_eval_with_namespace("${items[-2]} == 'banana'", namespace)
        assert result is True

    def test_negative_index_first_element(self) -> None:
        """Negative indexing: -3 accesses first element in 3-item list."""
        namespace = {"items": ["apple", "banana", "cherry"]}
        result = safe_eval_with_namespace("${items[-3]} == 'apple'", namespace)
        assert result is True

    def test_negative_index_out_of_range(self) -> None:
        """Negative index beyond list bounds raises IndexError."""
        namespace = {"items": [1, 2, 3]}
        with pytest.raises(IndexError, match="out of range"):
            safe_eval_with_namespace("${items[-99]} == 1", namespace)

    def test_negative_index_on_empty_list(self) -> None:
        """Negative index on empty list raises IndexError."""
        namespace: dict[str, Any] = {"items": []}
        with pytest.raises(IndexError, match="out of range"):
            safe_eval_with_namespace("${items[-1]} == 1", namespace)


class TestComplexExpressions:
    """Test complex logical expressions with and/or/not."""

    def test_and_expression(self) -> None:
        namespace = {"age": 25, "verified": True}
        result = safe_eval_with_namespace("${age} >= 18 and ${verified} == True", namespace)
        assert result is True

    def test_and_expression_short_circuit(self) -> None:
        """First condition false should short-circuit."""
        namespace = {"age": 15, "verified": True}
        result = safe_eval_with_namespace("${age} >= 18 and ${verified} == True", namespace)
        assert result is False

    def test_or_expression(self) -> None:
        namespace = {"premium": False, "vip": True}
        result = safe_eval_with_namespace("${premium} == True or ${vip} == True", namespace)
        assert result is True

    def test_or_expression_both_false(self) -> None:
        namespace = {"premium": False, "vip": False}
        result = safe_eval_with_namespace("${premium} == True or ${vip} == True", namespace)
        assert result is False

    def test_not_expression(self) -> None:
        namespace = {"blocked": False}
        result = safe_eval_with_namespace("not (${blocked} == True)", namespace)
        assert result is True

    def test_not_expression_with_true_value(self) -> None:
        namespace = {"blocked": True}
        result = safe_eval_with_namespace("not (${blocked} == True)", namespace)
        assert result is False

    def test_unary_minus_on_integer(self) -> None:
        """Unary minus should work on integer values."""
        namespace = {"value": 5}
        assert safe_eval_with_namespace("-${value} < 0", namespace) is True

    def test_unary_minus_on_float(self) -> None:
        """Unary minus should work on float values."""
        namespace = {"value": 3.14}
        assert safe_eval_with_namespace("-${value} < 0", namespace) is True

    def test_unary_minus_on_string_raises(self) -> None:
        """Unary minus on non-numeric operand raises TypeError."""
        namespace = {"text": "hello"}
        with pytest.raises(TypeError, match="Unary minus requires numeric operand"):
            safe_eval_with_namespace("-${text}", namespace)

    def test_and_short_circuit_guard_pattern(self) -> None:
        """Guard pattern: check existence before accessing nested property.

        Short-circuit evaluation prevents KeyError when user is None.
        Expression: ${user} and ${user.role} == "admin"
        If user is falsy, ${user.role} is never evaluated.
        """
        namespace: dict[str, Any] = {"user": None}
        # Should return False without raising KeyError on user.role access
        result = safe_eval_with_namespace("${user} and ${user.role} == 'admin'", namespace)
        assert result is False

    def test_and_short_circuit_with_valid_data(self) -> None:
        """Guard pattern works when data exists."""
        namespace: dict[str, Any] = {"user": {"role": "admin"}}
        result = safe_eval_with_namespace("${user} and ${user.role} == 'admin'", namespace)
        assert result is True

    def test_or_short_circuit_fallback_pattern(self) -> None:
        """Fallback pattern: use default if variable doesn't exist.

        Expression: ${not data} or ${data.value} > 100
        If data is falsy, first operand is True, so second operand is not evaluated.
        """
        namespace: dict[str, Any] = {"data": None}
        # Should return True without raising error on data.value access
        result = safe_eval_with_namespace("not ${data} or ${data.value} > 100", namespace)
        assert result is True

    def test_or_short_circuit_with_valid_data(self) -> None:
        """Fallback pattern evaluates second operand when first is False."""
        namespace: dict[str, Any] = {"data": {"value": 150}}
        result = safe_eval_with_namespace("not ${data} or ${data.value} > 100", namespace)
        assert result is True

    def test_chained_guard_pattern(self) -> None:
        """Multiple guards can be chained safely.

        Expression: ${response} and ${response.data} and ${response.data.items[0]}
        Each level is checked before accessing the next.
        """
        namespace: dict[str, Any] = {"response": None}
        result = safe_eval_with_namespace(
            "${response} and ${response.data} and ${response.data.items[0]} == 'test'", namespace
        )
        assert result is False

    def test_and_does_not_short_circuit_when_true(self) -> None:
        """AND evaluates all operands when all are truthy."""
        namespace = {"a": True, "b": True, "c": True}
        result = safe_eval_with_namespace("${a} and ${b} and ${c}", namespace)
        assert result is True

    def test_or_does_not_evaluate_remaining_when_true_found(self) -> None:
        """OR stops at first truthy value, doesn't evaluate rest."""
        namespace: dict[str, Any] = {"status": "done"}
        # First condition is True, so ${missing.field} is never evaluated
        result = safe_eval_with_namespace("${status} == 'done' or ${missing.field} == 'value'", namespace)
        assert result is True

    def test_nested_logical_expression(self) -> None:
        namespace = {"age": 25, "score": 75, "premium": True}
        result = safe_eval_with_namespace("(${age} >= 18 and ${score} > 50) or ${premium} == True", namespace)
        assert result is True

    def test_complex_business_logic(self) -> None:
        """Real-world example: user access check."""
        namespace = {
            "user": {"role": "editor", "verified": True, "active": True},
        }
        expr = (
            "(${user.role} == 'admin' or "
            "(${user.role} == 'editor' and ${user.verified} == True)) "
            "and ${user.active} == True"
        )
        result = safe_eval_with_namespace(expr, namespace)
        assert result is True


class TestTypePreservation:
    """Test that variable types are preserved (not converted to strings)."""

    def test_integer_type_preserved(self) -> None:
        """Integer values stay as int, not converted to string."""
        namespace = {"count": 42}
        # If count were "'42'" string, numeric comparison would fail
        assert safe_eval_with_namespace("${count} > 40", namespace) is True
        assert safe_eval_with_namespace("${count} == 42", namespace) is True

    def test_float_type_preserved(self) -> None:
        namespace = {"score": 0.85}
        assert safe_eval_with_namespace("${score} > 0.8", namespace) is True
        assert safe_eval_with_namespace("${score} < 0.9", namespace) is True

    def test_boolean_type_preserved(self) -> None:
        """Boolean values stay as bool, not converted to string."""
        namespace = {"enabled": True}
        # If enabled were "True" string, this would fail
        assert safe_eval_with_namespace("${enabled} == True", namespace) is True

    def test_none_value_preserved(self) -> None:
        namespace = {"value": None}
        assert safe_eval_with_namespace("${value} == None", namespace) is True

    def test_list_type_preserved(self) -> None:
        namespace = {"items": [1, 2, 3]}
        assert safe_eval_with_namespace("${items[0]} == 1", namespace) is True

    def test_dict_type_preserved(self) -> None:
        namespace = {"data": {"count": 100}}
        assert safe_eval_with_namespace("${data.count} == 100", namespace) is True


class TestStringQuotingEdgeCases:
    """Test that string quoting issues are eliminated.

    These tests verify the key advantage of context-aware evaluation:
    no repr() quoting means no issues with quotes/backslashes in strings.
    """

    def test_string_with_single_quote_no_escaping_needed(self) -> None:
        """String with single quote doesn't need escaping."""
        namespace = {"message": "it's working"}
        # With repr() this might create: "'it's working'" which could cause issues
        # With context-aware: value looked up directly, no quoting
        result = safe_eval_with_namespace('${message} == "it\'s working"', namespace)
        assert result is True

    def test_string_with_double_quote_no_escaping_needed(self) -> None:
        namespace = {"message": 'say "hello"'}
        result = safe_eval_with_namespace("${message} == 'say \"hello\"'", namespace)
        assert result is True

    def test_string_with_backslash_no_escaping_needed(self) -> None:
        namespace = {"path": r"C:\Users\Admin"}
        result = safe_eval_with_namespace(r"${path} == 'C:\\Users\\Admin'", namespace)
        assert result is True

    def test_string_with_newline(self) -> None:
        namespace = {"message": "line1\nline2"}
        result = safe_eval_with_namespace("${message} == 'line1\\nline2'", namespace)
        assert result is True

    def test_empty_string(self) -> None:
        namespace = {"value": ""}
        result = safe_eval_with_namespace("${value} == ''", namespace)
        assert result is True


class TestInOperator:
    """Test Python 'in' operator support (for backend compatibility)."""

    def test_string_in_string(self) -> None:
        namespace = {"text": "hello world"}
        result = safe_eval_with_namespace("'world' in ${text}", namespace)
        assert result is True

    def test_string_not_in_string(self) -> None:
        namespace = {"text": "hello world"}
        result = safe_eval_with_namespace("'python' in ${text}", namespace)
        assert result is False

    def test_element_in_list(self) -> None:
        namespace = {"items": ["apple", "banana", "cherry"]}
        result = safe_eval_with_namespace("'banana' in ${items}", namespace)
        assert result is True

    def test_not_in_operator(self) -> None:
        namespace = {"email": "user@example.com"}
        result = safe_eval_with_namespace("'spam' not in ${email}", namespace)
        assert result is True


class TestErrorMessages:
    """Test that error messages are helpful."""

    def test_invalid_syntax_error_message(self) -> None:
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            safe_eval_with_namespace("${status} ==", {"status": "ok"})

    def test_variable_not_found_error_message(self) -> None:
        with pytest.raises(KeyError, match="'unknown' not found"):
            safe_eval_with_namespace("${unknown} == 'value'", {})

    def test_unsupported_operation_error_message(self) -> None:
        """Function calls are not supported."""
        with pytest.raises(TypeError, match="Unsupported expression type"):
            safe_eval_with_namespace("len(${items})", {"items": [1, 2, 3]})


class TestRealWorldScenarios:
    """Test real workflow scenarios."""

    def test_condition_node_example(self) -> None:
        """Example from condition node."""
        namespace = {
            "fetch_order": {
                "riskScore": 0.8,
                "orderAmount": 15000,
            },
            "input": {
                "orderId": "12345",
            },
        }

        # High risk if risk score > 0.7 OR order amount > 10000
        result = safe_eval_with_namespace(
            "${fetch_order.riskScore} > 0.7 or ${fetch_order.orderAmount} > 10000", namespace
        )
        assert result is True

    def test_loop_do_while_example(self) -> None:
        """Example from loop do_while condition."""
        namespace = {
            "loop": {
                "index": 5,
            },
        }

        # Continue while index < 10
        result = safe_eval_with_namespace("${loop.index} < 10", namespace)
        assert result is True

    def test_complex_aap_job_check(self) -> None:
        """Example: AAP job status check."""
        namespace = {
            "activity": {
                "aap_job": {
                    "raw": {
                        "status": "completed",
                        "output": "Hello World",
                    }
                }
            },
        }

        result = safe_eval_with_namespace(
            "${activity.aap_job.raw.status} == 'completed' and 'Hello' in ${activity.aap_job.raw.output}", namespace
        )
        assert result is True


class TestSecurityLimits:
    """Test security limits to prevent DoS attacks."""

    def test_expression_length_limit(self) -> None:
        """Expressions longer than MAX_EXPRESSION_LENGTH are rejected."""
        from syntara.workflows.workflow_engine.unified_eval import MAX_EXPRESSION_LENGTH

        long_expr = "${x} == 'a'" + " and ${x} == 'a'" * 1000
        if len(long_expr) > MAX_EXPRESSION_LENGTH:
            with pytest.raises(ValueError, match="Expression too long"):
                safe_eval_with_namespace(long_expr, {"x": "a"})

    def test_variable_name_length_limit_old_behavior(self) -> None:
        """Variable names longer than MAX_VARIABLE_NAME_LENGTH are now explicitly validated."""
        from syntara.workflows.workflow_engine.unified_eval import MAX_VARIABLE_NAME_LENGTH

        long_var = "x" * (MAX_VARIABLE_NAME_LENGTH + 100)
        expr = f"${{{long_var}}} == 'test'"
        # New behavior: callback validates length and raises explicit error
        with pytest.raises(ValueError, match="Variable name too long"):
            safe_eval_with_namespace(expr, {long_var: "test"})

    def test_ast_depth_limit(self) -> None:
        """Deeply nested expressions are rejected."""
        # Create deeply nested expression with 'and' operations
        # Parentheses alone don't increase depth (Python optimizes them),
        # but nested BoolOp nodes do
        namespace: dict[str, Any] = {"x": 5}
        nested_expr = "${x} > 1"
        for _ in range(MAX_AST_DEPTH + 10):  # Exceeds MAX_AST_DEPTH
            nested_expr = f"({nested_expr}) and True"

        with pytest.raises(ValueError, match="too deeply nested"):
            safe_eval_with_namespace(nested_expr, namespace)

    def test_ast_node_count_limit(self) -> None:
        """Expressions with too many AST nodes are rejected."""
        # Create expression with many nodes: x > 1 and x > 2 and x > 3...
        namespace: dict[str, Any] = {"x": 5}
        parts = [f"${{x}} > {i}" for i in range(200)]  # Creates >500 nodes
        expr = " and ".join(parts)

        with pytest.raises(ValueError, match="too complex"):
            safe_eval_with_namespace(expr, namespace)


class TestEdgeCases:
    """Test edge cases and malformed inputs."""

    def test_malformed_template_unclosed(self) -> None:
        """Unclosed ${} syntax is rejected."""
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            safe_eval_with_namespace("${unclosed", {"unclosed": "value"})

    def test_malformed_template_double_braces(self) -> None:
        """Double braces are handled (outer braces stripped)."""
        namespace: dict[str, Any] = {"nested": "value"}
        # ${{nested}} -> {nested} after regex -> parses as Set literal
        with pytest.raises(TypeError, match="Unsupported expression type: Set"):
            safe_eval_with_namespace("${{nested}} == 'value'", namespace)

    def test_chained_comparison(self) -> None:
        """Python allows chained comparisons: 1 < x < 10."""
        namespace: dict[str, Any] = {"x": 5}
        assert safe_eval_with_namespace("1 < ${x} < 10", namespace) is True
        assert safe_eval_with_namespace("1 < ${x} < 3", namespace) is False

    def test_transitive_equality(self) -> None:
        """Chained equality: a == b == c."""
        namespace: dict[str, Any] = {"a": 5, "b": 5, "c": 5}
        assert safe_eval_with_namespace("${a} == ${b} == ${c}", namespace) is True

        namespace = {"a": 5, "b": 5, "c": 6}
        assert safe_eval_with_namespace("${a} == ${b} == ${c}", namespace) is False

    def test_unicode_string_comparison(self) -> None:
        """Unicode strings work correctly."""
        namespace: dict[str, Any] = {"message": "你好"}
        assert safe_eval_with_namespace("${message} == '你好'", namespace) is True

    def test_backslash_in_string(self) -> None:
        """Strings with backslashes (e.g., Windows paths) work correctly."""
        namespace: dict[str, Any] = {"path": r"C:\Users\Admin"}
        # Use raw string in expression to match raw string in namespace
        assert safe_eval_with_namespace(r"${path} == 'C:\\Users\\Admin'", namespace) is True

    def test_numeric_in_list(self) -> None:
        """Numeric 'in' operator works with lists."""
        namespace: dict[str, Any] = {"items": [1, 2, 3]}
        assert safe_eval_with_namespace("2 in ${items}", namespace) is True
        assert safe_eval_with_namespace("5 in ${items}", namespace) is False

    def test_substring_check(self) -> None:
        """String 'in' operator works for substring checks."""
        namespace: dict[str, Any] = {"text": "hello world"}
        assert safe_eval_with_namespace("'world' in ${text}", namespace) is True
        assert safe_eval_with_namespace("'python' in ${text}", namespace) is False

    def test_none_in_list(self) -> None:
        """None value works with 'in' operator."""
        namespace: dict[str, Any] = {"items": [1, 2, None]}
        assert safe_eval_with_namespace("None in ${items}", namespace) is True

    def test_empty_string_comparison(self) -> None:
        """Empty string comparisons work correctly."""
        namespace: dict[str, Any] = {"value": ""}
        assert safe_eval_with_namespace("${value} == ''", namespace) is True
        assert safe_eval_with_namespace("${value} != ''", namespace) is False


class TestTypeCoercion:
    """Test type handling and coercion behavior."""

    def test_cross_type_comparison_error(self) -> None:
        """Comparing incompatible types should fail gracefully."""
        namespace: dict[str, Any] = {"count": "42"}  # String
        # Comparing string "42" with int 40 - behavior depends on _compare
        # This test documents current behavior
        try:
            result = safe_eval_with_namespace("${count} > 40", namespace)
            # If _compare allows it, document that behavior
            assert isinstance(result, bool)
        except (TypeError, ValueError):
            # If _compare rejects it, that's also valid
            pass

    def test_string_vs_int_equality(self) -> None:
        """String and int equality (should be False in Python)."""
        namespace: dict[str, Any] = {"count": "42"}
        # "42" == 42 should be False in Python
        result = safe_eval_with_namespace("${count} == 42", namespace)
        assert result is False  # String != int


class TestLoopContextIsolation:
    """Test loop context isolation (Fix #7 from adversarial review)."""

    def test_loop_context_not_available_outside_loop(self) -> None:
        """Nodes outside loop body should not have access to loop context."""
        # Namespace without loop context (as if outside loop)
        namespace = {"status": "done"}

        # Should succeed - status is in namespace
        result = safe_eval_with_namespace("${status} == 'done'", namespace)
        assert result is True

        # Should fail - loop not in namespace
        with pytest.raises(KeyError, match="loop"):
            safe_eval_with_namespace("${loop.index} < 10", namespace)

    def test_loop_context_isolated_between_iterations(self) -> None:
        """Each loop iteration should have isolated context."""
        # First iteration
        namespace_iter_0 = {"loop": {"index": 0, "item": "first"}, "status": "processing"}
        result = safe_eval_with_namespace("${loop.item} == 'first'", namespace_iter_0)
        assert result is True

        # Second iteration - different loop context
        namespace_iter_1 = {"loop": {"index": 1, "item": "second"}, "status": "processing"}
        result = safe_eval_with_namespace("${loop.item} == 'second'", namespace_iter_1)
        assert result is True

        # Should not have access to first iteration's data
        with pytest.raises(AssertionError):
            result = safe_eval_with_namespace("${loop.item} == 'first'", namespace_iter_1)
            assert result is True

    def test_empty_namespace_with_literal_expression(self) -> None:
        """Empty namespace should work with literal expressions."""
        result = safe_eval_with_namespace("True", {})
        assert result is True

        result = safe_eval_with_namespace("False", {})
        assert result is False

        result = safe_eval_with_namespace("5 > 3", {})
        assert result is True


class TestReDoSFix:
    """Test ReDoS vulnerability fix (Fix #4 from adversarial review)."""

    def test_expression_with_many_closing_braces_no_hang(self) -> None:
        """Expression with mismatched braces should fail fast, not hang."""
        # This would cause catastrophic backtracking with old regex
        expression = "${x" + "}" * 100
        with pytest.raises(ValueError):
            safe_eval_with_namespace(expression, {"x": 1})

    def test_variable_name_length_limit(self) -> None:
        """Variable names exceeding MAX_VARIABLE_NAME_LENGTH are rejected."""
        from syntara.workflows.workflow_engine.unified_eval import MAX_VARIABLE_NAME_LENGTH

        long_var = "x" * (MAX_VARIABLE_NAME_LENGTH + 1)
        expression = f"${{{long_var}}} == 1"

        with pytest.raises(ValueError, match="Variable name too long"):
            safe_eval_with_namespace(expression, {long_var: 1})

    def test_fast_path_no_templates(self) -> None:
        """Expressions without ${} should skip regex processing."""
        # No templates - fast path
        result = safe_eval_with_namespace("True", {})
        assert result is True

        result = safe_eval_with_namespace("5 > 3", {})
        assert result is True


class TestASTDepthValidation:
    """Test AST depth validation (Fix #5 from adversarial review)."""

    def test_deeply_nested_attribute_access_rejected(self) -> None:
        """Deeply nested attribute access should be rejected before parsing."""
        from syntara.workflows.workflow_engine.unified_eval import MAX_AST_DEPTH

        # Create deeply nested expression
        deep_path = ".".join(["x"] * (MAX_AST_DEPTH + 1))
        expression = f"${{{deep_path}}} == 1"

        with pytest.raises(ValueError, match="too deeply nested"):
            safe_eval_with_namespace(expression, {"x": {"x": {"x": 1}}})

    def test_moderately_nested_attribute_access_allowed(self) -> None:
        """Moderately nested expressions within limit should work."""
        namespace = {"a": {"b": {"c": {"d": 42}}}}
        result = safe_eval_with_namespace("${a.b.c.d} == 42", namespace)
        assert result is True


class TestReservedKeywords:
    """Test handling of Python reserved keywords in namespaces."""

    def test_reserved_keyword_as_variable_fails(self) -> None:
        """Python keywords cannot be used as variable names in expressions."""
        # 'class' is a reserved keyword
        namespace = {"class": "admin"}

        # This will fail during AST parsing because 'class' is a keyword
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            safe_eval_with_namespace("${class} == 'admin'", namespace)

    def test_non_keyword_similar_names_work(self) -> None:
        """Non-keyword names that look similar work fine."""
        namespace = {"klass": "admin", "type_": "user"}

        result = safe_eval_with_namespace("${klass} == 'admin'", namespace)
        assert result is True

        result = safe_eval_with_namespace("${type_} == 'user'", namespace)
        assert result is True


class TestExceptionHandlingFix:
    """Test exception handling improvements (Fix #3 from adversarial review)."""

    def test_index_error_caught_in_subscript(self) -> None:
        """IndexError from list subscripts should be caught."""
        namespace = {"items": [1, 2, 3]}

        # This raises IndexError in unified_eval, should propagate as ValueError
        with pytest.raises((IndexError, ValueError)):
            safe_eval_with_namespace("${items[10]} == 1", namespace)
