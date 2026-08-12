"""Unit tests for template resolution utilities.

This module tests the template expression resolution utilities used by workflow activities.
"""

from typing import Any

import pytest

from syntara.workflows.utils.template_resolution import resolve_parameter_templates, resolve_value
from syntara.workflows.workflow_engine.expression_resolver import ExpressionResolver


class TestResolveValue:
    """Tests for resolve_value function."""

    def test_resolve_primitive_string_no_template(self) -> None:
        """Test resolving plain string without template expressions."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {"name": "Alice"}}

        result = resolve_value("plain text", resolver, workflow_state)
        assert result == "plain text"

    def test_resolve_primitive_string_with_template(self) -> None:
        """Test resolving string with template expression."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {"name": "Alice"}}

        result = resolve_value("${input.name}", resolver, workflow_state)
        assert result == "Alice"

    def test_resolve_primitive_integer(self) -> None:
        """Test resolving integer value."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {}

        result = resolve_value(42, resolver, workflow_state)
        assert result == 42

    def test_resolve_primitive_float(self) -> None:
        """Test resolving float value."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {}

        result = resolve_value(3.14, resolver, workflow_state)
        assert result == pytest.approx(3.14)

    def test_resolve_primitive_boolean(self) -> None:
        """Test resolving boolean value."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {}

        boolean_value = True
        result = resolve_value(boolean_value, resolver, workflow_state)
        assert result is True

    def test_resolve_primitive_none(self) -> None:
        """Test resolving None value."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {}

        result = resolve_value(None, resolver, workflow_state)
        assert result is None

    def test_resolve_dict_flat(self) -> None:
        """Test resolving flat dictionary with template expressions."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {"timeout": 60, "retries": 3}}

        value = {
            "timeout": "${input.timeout}",
            "max_attempts": "${input.retries}",
            "static_value": "constant",
        }

        result = resolve_value(value, resolver, workflow_state)
        assert result == {"timeout": 60, "max_attempts": 3, "static_value": "constant"}

    def test_resolve_dict_nested(self) -> None:
        """Test resolving nested dictionary with template expressions."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {"user_id": 123, "api_key": "secret123"}}

        value = {
            "authentication": {"user_id": "${input.user_id}", "api_key": "${input.api_key}"},
            "metadata": {"static": "value"},
        }

        result = resolve_value(value, resolver, workflow_state)
        assert result == {
            "authentication": {"user_id": 123, "api_key": "secret123"},
            "metadata": {"static": "value"},
        }

    def test_resolve_list_of_primitives(self) -> None:
        """Test resolving list of primitive values with templates."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {"host1": "server1.com", "host2": "server2.com"}}

        value = ["${input.host1}", "${input.host2}", "server3.com"]

        result = resolve_value(value, resolver, workflow_state)
        assert result == ["server1.com", "server2.com", "server3.com"]

    def test_resolve_list_of_dicts(self) -> None:
        """Test resolving list of dictionaries with template expressions."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {"port": 8080, "protocol": "https"}}

        value = [
            {"host": "server1.com", "port": "${input.port}"},
            {"host": "server2.com", "port": 9090, "protocol": "${input.protocol}"},
        ]

        result = resolve_value(value, resolver, workflow_state)
        assert result == [
            {"host": "server1.com", "port": 8080},
            {"host": "server2.com", "port": 9090, "protocol": "https"},
        ]

    def test_resolve_deeply_nested_structure(self) -> None:
        """Test resolving deeply nested structure with mixed types."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {"db_name": "production", "replicas": 3, "enabled": True}}

        value = {
            "database": {
                "name": "${input.db_name}",
                "config": {"replicas": "${input.replicas}", "features": ["replication", "backup"]},
            },
            "enabled": "${input.enabled}",
            "servers": [{"host": "db1.com"}, {"host": "db2.com", "port": "${input.replicas}"}],
        }

        result = resolve_value(value, resolver, workflow_state)
        assert result == {
            "database": {
                "name": "production",
                "config": {"replicas": 3, "features": ["replication", "backup"]},
            },
            "enabled": True,
            "servers": [{"host": "db1.com"}, {"host": "db2.com", "port": 3}],
        }


class TestResolveConfigTemplates:
    """Tests for resolve_parameter_templates function."""

    def test_resolve_empty_config(self) -> None:
        """Test resolving empty config dictionary."""
        workflow_state: dict[str, Any] = {}

        result = resolve_parameter_templates({}, workflow_state)
        assert result == {}

    def test_resolve_config_no_templates(self) -> None:
        """Test resolving config without template expressions."""
        workflow_state: dict[str, Any] = {}

        config = {"timeout": 30, "language": "python", "enabled": True}

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {"timeout": 30, "language": "python", "enabled": True}

    def test_resolve_config_with_template_timeout(self) -> None:
        """Test resolving config with template expression in timeout field."""
        workflow_state: dict[str, Any] = {"inputs": {"custom_timeout": 60}}

        config = {"language": "bash", "timeout": "${input.custom_timeout}", "code": "echo hello"}

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {"language": "bash", "timeout": 60, "code": "echo hello"}

    def test_resolve_config_aap_job_template(self) -> None:
        """Test resolving AAP job template config with multiple template fields."""
        workflow_state: dict[str, Any] = {
            "inputs": {"job_template_id": 42, "verbosity": 2, "inventory": 10, "timeout": 3600}
        }

        config = {
            "job_template_id": "${input.job_template_id}",
            "verbosity": "${input.verbosity}",
            "inventory": "${input.inventory}",
            "timeout": "${input.timeout}",
            "extra_vars": {"key": "value"},
        }

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {
            "job_template_id": 42,
            "verbosity": 2,
            "inventory": 10,
            "timeout": 3600,
            "extra_vars": {"key": "value"},
        }

    def test_resolve_config_with_nested_extra_vars(self) -> None:
        """Test resolving config with nested template expressions in extra_vars."""
        workflow_state: dict[str, Any] = {
            "inputs": {"app_name": "myapp", "version": "2.0.0", "env": "production", "timeout": 1800}
        }

        config = {
            "job_template_id": 42,
            "timeout": "${input.timeout}",
            "extra_vars": {
                "app_name": "${input.app_name}",
                "app_version": "${input.version}",
                "deployment_env": "${input.env}",
                "features": ["logging", "monitoring"],
            },
        }

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {
            "job_template_id": 42,
            "timeout": 1800,
            "extra_vars": {
                "app_name": "myapp",
                "app_version": "2.0.0",
                "deployment_env": "production",
                "features": ["logging", "monitoring"],
            },
        }

    def test_resolve_config_api_executor(self) -> None:
        """Test resolving API executor config with template expressions."""
        workflow_state: dict[str, Any] = {"inputs": {"api_timeout": 30, "user_id": 123}}

        config = {
            "method": "GET",
            "url": "https://api.example.com/users/${input.user_id}",
            "timeout": "${input.api_timeout}",
            "headers": {"Authorization": "Bearer ${secrets.api_token}"},
        }

        # Note: secrets need to be in inputs for this test
        workflow_state["inputs"]["secrets"] = {"api_token": "abc123"}

        result = resolve_parameter_templates(config, workflow_state)
        assert result["method"] == "GET"
        assert result["url"] == "https://api.example.com/users/123"
        assert result["timeout"] == 30

    def test_resolve_config_script_executor(self) -> None:
        """Test resolving script executor config with template expressions."""
        workflow_state: dict[str, Any] = {"inputs": {"script_timeout": 120, "api_key": "secret"}}

        config = {
            "language": "python",
            "code": "print('Hello World')",
            "timeout": "${input.script_timeout}",
            "environment": {"API_KEY": "${input.api_key}", "DEBUG": "true"},
        }

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {
            "language": "python",
            "code": "print('Hello World')",
            "timeout": 120,
            "environment": {"API_KEY": "secret", "DEBUG": "true"},
        }

    def test_resolve_config_with_custom_resolver(self) -> None:
        """Test resolving config with a custom resolver instance."""
        # Create a custom resolver
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {"value": 100}}

        config = {"field": "${input.value}"}

        result = resolve_parameter_templates(config, workflow_state, resolver=resolver)
        assert result == {"field": 100}

    def test_resolve_config_creates_default_resolver(self) -> None:
        """Test that resolve_parameter_templates creates a default resolver when not provided."""
        workflow_state: dict[str, Any] = {"inputs": {"value": 42}}

        config = {"field": "${input.value}"}

        # Call without providing resolver
        result = resolve_parameter_templates(config, workflow_state)
        assert result == {"field": 42}

    def test_resolve_config_mixed_types(self) -> None:
        """Test resolving config with mixed primitive types."""
        workflow_state: dict[str, Any] = {
            "inputs": {"timeout": 60, "retries": 3, "enabled": True, "name": "test", "ratio": 0.75}
        }

        config = {
            "timeout": "${input.timeout}",
            "max_attempts": "${input.retries}",
            "enabled": "${input.enabled}",
            "name": "${input.name}",
            "ratio": "${input.ratio}",
            "static_int": 100,
            "static_str": "constant",
        }

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {
            "timeout": 60,
            "max_attempts": 3,
            "enabled": True,
            "name": "test",
            "ratio": 0.75,
            "static_int": 100,
            "static_str": "constant",
        }

    def test_resolve_config_list_of_dictionaries(self) -> None:
        """Test resolving config with list of dictionaries containing templates."""
        workflow_state: dict[str, Any] = {"inputs": {"replica_count": 3, "port": 8080}}

        config = {
            "servers": [
                {"name": "server1", "replicas": "${input.replica_count}"},
                {"name": "server2", "port": "${input.port}"},
            ]
        }

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {"servers": [{"name": "server1", "replicas": 3}, {"name": "server2", "port": 8080}]}

    def test_resolve_config_preserves_none_values(self) -> None:
        """Test that None values are preserved during resolution."""
        workflow_state: dict[str, Any] = {"inputs": {"value": 42}}

        config = {"field1": "${input.value}", "field2": None, "field3": "test"}

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {"field1": 42, "field2": None, "field3": "test"}


class TestTemplateResolutionEdgeCases:
    """Tests for edge cases and error handling."""

    def test_resolve_value_with_undefined_input(self) -> None:
        """Test resolving template with undefined input field returns None."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {}}

        # Known scope ('input') but missing field returns None via _navigate_nested_path
        value = "${input.undefined_field}"
        result = resolve_value(value, resolver, workflow_state)
        assert result is None

    def test_resolve_value_with_unknown_scope_raises(self) -> None:
        """Test resolving template with unknown scope raises KeyError."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {}}

        value = "${does_not_exist.output.data}"
        with pytest.raises(KeyError, match="does_not_exist"):
            resolve_value(value, resolver, workflow_state)

    def test_resolve_config_with_empty_workflow_state(self) -> None:
        """Test resolving config with empty workflow state."""
        workflow_state: dict[str, Any] = {"inputs": {}}

        config = {"static_field": "value", "number": 42}

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {"static_field": "value", "number": 42}

    def test_resolve_value_empty_list(self) -> None:
        """Test resolving empty list."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {}

        result = resolve_value([], resolver, workflow_state)
        assert result == []

    def test_resolve_value_empty_dict(self) -> None:
        """Test resolving empty dict."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {}

        result = resolve_value({}, resolver, workflow_state)
        assert result == {}

    def test_resolve_config_all_fields_static(self) -> None:
        """Test resolving config where all fields are static (no templates)."""
        workflow_state: dict[str, Any] = {"inputs": {"unused": 123}}

        config = {
            "timeout": 30,
            "language": "python",
            "code": "print('hello')",
            "environment": {"KEY": "value"},
        }

        result = resolve_parameter_templates(config, workflow_state)
        assert result == config

    def test_resolve_config_all_fields_templates(self) -> None:
        """Test resolving config where all fields are template expressions."""
        workflow_state: dict[str, Any] = {
            "inputs": {"timeout": 60, "language": "bash", "code": "echo test", "key": "secret"}
        }

        config = {
            "timeout": "${input.timeout}",
            "language": "${input.language}",
            "code": "${input.code}",
            "environment": {"KEY": "${input.key}"},
        }

        result = resolve_parameter_templates(config, workflow_state)
        assert result == {
            "timeout": 60,
            "language": "bash",
            "code": "echo test",
            "environment": {"KEY": "secret"},
        }

    def test_resolve_config_nonexistent_activity_raises(self) -> None:
        """Test that referencing a non-existent activity in config raises KeyError."""
        workflow_state: dict[str, Any] = {"inputs": {}, "activity_outputs": {}}

        config = {"environment": {"VALUE": "${does_not_exist.output.data}"}}

        with pytest.raises(KeyError, match="does_not_exist"):
            resolve_parameter_templates(config, workflow_state)


class TestUnresolvableExpressionRegression:
    """Regression tests: unresolvable expressions must raise, not return None."""

    def test_nonexistent_node_reference_raises(self) -> None:
        """Referencing a non-existent node should raise KeyError."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {
            "inputs": {},
            "activity_outputs": {"real_node": {"output": {"data": "ok"}}},
        }

        with pytest.raises(KeyError, match="ghost_node"):
            resolver.resolve_expression("${ghost_node.output.data}", workflow_state)

    def test_existing_node_reference_succeeds(self) -> None:
        """Referencing an existing node should resolve correctly."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {
            "inputs": {},
            "activity_outputs": {"real_node": {"output": {"data": "ok"}}},
        }

        result = resolver.resolve_expression("${real_node.output.data}", workflow_state)
        assert result == "ok"

    def test_multiple_expressions_with_one_invalid_raises(self) -> None:
        """A string with multiple expressions should raise if any reference is invalid."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {
            "inputs": {"name": "Alice"},
            "activity_outputs": {},
        }

        with pytest.raises(KeyError, match="missing_node"):
            resolver.resolve_expression("Hello ${input.name}, result: ${missing_node.output}", workflow_state)

    def test_nested_dict_with_invalid_reference_raises(self) -> None:
        """Nested dicts containing invalid references should raise on resolution."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {}, "activity_outputs": {}}

        value = {"level1": {"level2": "${phantom.value}"}}
        with pytest.raises(KeyError, match="phantom"):
            resolve_value(value, resolver, workflow_state)

    def test_list_with_invalid_reference_raises(self) -> None:
        """Lists containing invalid references should raise on resolution."""
        resolver = ExpressionResolver()
        workflow_state: dict[str, Any] = {"inputs": {}, "activity_outputs": {}}

        value = ["${ghost.x}", "static"]
        with pytest.raises(KeyError, match="ghost"):
            resolve_value(value, resolver, workflow_state)
