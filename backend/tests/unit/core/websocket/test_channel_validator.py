"""Tests for WebSocket channel validator."""

import types
from typing import Any

from syntara.core.websocket.channel_validator import (
    ChannelValidationResult,
    check_missing_handlers,
    check_orphaned_handlers,
    get_handler_function_names,
    get_server_pathname,
    is_snake_case,
    normalize_channel_name,
    validate_channel_addresses,
    validate_channel_mappings,
    validate_naming_convention,
)


class TestNormalizeChannelName:
    """Tests for normalize_channel_name function."""

    def test_kebab_case_to_snake_case(self) -> None:
        """Test converting kebab-case to snake_case."""
        assert normalize_channel_name("agent-events") == "agent_events"
        assert normalize_channel_name("my-complex-name") == "my_complex_name"

    def test_already_snake_case(self) -> None:
        """Test names already in snake_case."""
        assert normalize_channel_name("coffee") == "coffee"
        assert normalize_channel_name("agent_events") == "agent_events"

    def test_multiple_hyphens(self) -> None:
        """Test names with multiple hyphens."""
        assert normalize_channel_name("one-two-three-four") == "one_two_three_four"


class TestIsSnakeCase:
    """Tests for is_snake_case function."""

    def test_valid_snake_case(self) -> None:
        """Test valid snake_case names."""
        assert is_snake_case("coffee") is True
        assert is_snake_case("agent_events") is True
        assert is_snake_case("my_channel_name") is True

    def test_invalid_kebab_case(self) -> None:
        """Test kebab-case is not snake_case."""
        assert is_snake_case("agent-events") is False
        assert is_snake_case("my-channel") is False

    def test_invalid_camel_case(self) -> None:
        """Test camelCase is not snake_case."""
        assert is_snake_case("agentEvents") is False
        assert is_snake_case("MyChannel") is False

    def test_edge_cases(self) -> None:
        """Test edge cases."""
        assert is_snake_case("a") is True
        assert is_snake_case("a1") is True
        assert is_snake_case("a_1") is True
        assert is_snake_case("_invalid") is False  # Can't start with underscore
        assert is_snake_case("1invalid") is False  # Can't start with number


class TestGetHandlerFunctionNames:
    """Tests for get_handler_function_names function."""

    def test_empty_module(self) -> None:
        """Test module with no handler functions."""
        module = types.ModuleType("test_module")

        result = get_handler_function_names(module)

        assert result == {"handlers": [], "on_connect": []}

    def test_module_with_handlers(self) -> None:
        """Test module with handler functions."""
        module = types.ModuleType("test_module")

        async def handle_coffee(message: dict[str, object]) -> dict[str, object]:
            return {}

        async def handle_chat(message: dict[str, object]) -> dict[str, object]:
            return {}

        module.handle_coffee = handle_coffee  # type: ignore[attr-defined]
        module.handle_chat = handle_chat  # type: ignore[attr-defined]

        result = get_handler_function_names(module)

        assert set(result["handlers"]) == {"coffee", "chat"}
        assert result["on_connect"] == []

    def test_module_with_on_connect(self) -> None:
        """Test module with on_connect functions."""
        module = types.ModuleType("test_module")

        async def on_connect_chat(websocket, connection_id: str) -> None:
            pass

        async def on_connect_agent_events(websocket, connection_id: str) -> None:
            pass

        module.on_connect_chat = on_connect_chat  # type: ignore[attr-defined]
        module.on_connect_agent_events = on_connect_agent_events  # type: ignore[attr-defined]

        result = get_handler_function_names(module)

        assert result["handlers"] == []
        assert set(result["on_connect"]) == {"chat", "agent_events"}

    def test_module_with_both(self) -> None:
        """Test module with both handler and on_connect functions."""
        module = types.ModuleType("test_module")

        async def handle_coffee(message: dict[str, object]) -> dict[str, object]:
            return {}

        async def on_connect_chat(websocket, connection_id: str) -> None:
            pass

        module.handle_coffee = handle_coffee  # type: ignore[attr-defined]
        module.on_connect_chat = on_connect_chat  # type: ignore[attr-defined]

        result = get_handler_function_names(module)

        assert result["handlers"] == ["coffee"]
        assert result["on_connect"] == ["chat"]

    def test_module_with_non_functions(self) -> None:
        """Test module with non-function attributes."""
        module = types.ModuleType("test_module")

        async def handle_coffee(message: dict[str, object]) -> dict[str, object]:
            return {}

        module.handle_coffee = handle_coffee  # type: ignore[attr-defined]
        module.handle_invalid = "not a function"  # type: ignore[attr-defined]
        module.some_variable = 42  # type: ignore[attr-defined]

        result = get_handler_function_names(module)

        assert result["handlers"] == ["coffee"]
        assert result["on_connect"] == []


class TestChannelValidationResult:
    """Tests for ChannelValidationResult dataclass."""

    def test_initialization(self) -> None:
        """Test ChannelValidationResult initialization."""
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        assert result.component_name == "example"
        assert result.spec_path == "example.yaml"
        assert result.errors == []
        assert result.warnings == []
        assert result.channels_validated == 0
        assert result.handlers_validated == 0

    def test_is_valid_with_no_errors(self) -> None:
        """Test is_valid returns True when no errors."""
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        assert result.is_valid is True

    def test_is_valid_with_errors(self) -> None:
        """Test is_valid returns False when errors exist."""
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")
        result.errors.append("Test error")

        assert result.is_valid is False

    def test_add_error(self) -> None:
        """Test add_error method."""
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        result.add_error("Test error message")

        assert len(result.errors) == 1
        assert result.errors[0] == "Test error message"

    def test_add_warning(self) -> None:
        """Test add_warning method."""
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        result.add_warning("Test warning message")

        assert len(result.warnings) == 1
        assert result.warnings[0] == "Test warning message"


class TestValidateNamingConvention:
    """Tests for validate_naming_convention function."""

    def test_valid_snake_case_channels(self) -> None:
        """Test channels with valid snake_case names."""
        channels: dict[str, object] = {
            "coffee": {},
            "chat": {},
            "agent_events": {},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        validate_naming_convention(channels, result)

        assert len(result.errors) == 0

    def test_invalid_kebab_case_channels(self) -> None:
        """Test channels with invalid kebab-case names."""
        channels: dict[str, object] = {
            "agent-events": {},
            "my-channel": {},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        validate_naming_convention(channels, result)

        assert len(result.errors) == 2
        assert "agent-events" in result.errors[0]
        assert "agent_events" in result.errors[0]
        assert "my-channel" in result.errors[1]
        assert "my_channel" in result.errors[1]


class TestCheckMissingHandlers:
    """Tests for check_missing_handlers function."""

    def test_all_handlers_present(self) -> None:
        """Test when all channels have handlers."""
        spec: dict[str, Any] = {"operations": {}}
        channels: dict[str, object] = {"coffee": {}, "chat": {}}
        handler_functions: dict[str, list[str]] = {"handlers": ["coffee", "chat"], "on_connect": []}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_missing_handlers(channels, handler_functions, spec, result)

        assert len(result.warnings) == 0

    def test_missing_handler(self) -> None:
        """Test when a channel is missing its handler."""
        spec: dict[str, Any] = {"operations": {}}
        channels: dict[str, object] = {"coffee": {}, "chat": {}}
        handler_functions: dict[str, list[str]] = {"handlers": ["coffee"], "on_connect": []}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_missing_handlers(channels, handler_functions, spec, result)

        assert len(result.warnings) == 1
        assert "handle_chat" in result.warnings[0]
        assert "chat" in result.warnings[0]

    def test_kebab_case_channel_name(self) -> None:
        """Test missing handler detection with kebab-case channel name."""
        spec: dict[str, Any] = {"operations": {}}
        channels: dict[str, object] = {"agent-events": {}}
        handler_functions: dict[str, list[str]] = {"handlers": [], "on_connect": []}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_missing_handlers(channels, handler_functions, spec, result)

        assert len(result.warnings) == 1
        assert "handle_agent_events" in result.warnings[0]


class TestCheckMissingHandlersReceiveOnly:
    """Tests for check_missing_handlers with receive-only channels (Phase 3: AAP-58895)."""

    def test_missing_handler_bidirectional_warns(self) -> None:
        """Bidirectional channel without handler gets warning (existing behavior)."""
        spec: dict[str, Any] = {
            "operations": {},  # No operations = bidirectional
            "channels": {"coffee": {}},
        }
        channels: dict[str, object] = {"coffee": {}}
        handler_functions: dict[str, list[str]] = {"handlers": [], "on_connect": []}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_missing_handlers(channels, handler_functions, spec, result)

        assert len(result.warnings) == 1
        assert "handle_coffee" in result.warnings[0]

    def test_missing_handler_receive_only_no_warning(self) -> None:
        """Receive-only channel without handler does NOT get warning."""
        spec = {
            "operations": {
                "receiveEvents": {
                    "action": "receive",
                    "channel": {"$ref": "#/channels/tokens"},
                }
            },
            "channels": {"tokens": {}},
        }
        channels: dict[str, object] = {"tokens": {}}
        handler_functions: dict[str, list[str]] = {"handlers": [], "on_connect": ["tokens"]}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_missing_handlers(channels, handler_functions, spec, result)

        # No warning for receive-only channel
        assert len(result.warnings) == 0

    def test_mixed_channels_correct_warnings(self) -> None:
        """Mixed bidirectional and receive-only channels get appropriate warnings."""
        spec = {
            "operations": {
                "receiveTokens": {
                    "action": "receive",
                    "channel": {"$ref": "#/channels/tokens"},
                }
            },
            "channels": {
                "tokens": {},  # Receive-only
                "coffee": {},  # Bidirectional (no operations)
            },
        }
        channels: dict[str, object] = {"tokens": {}, "coffee": {}}
        handler_functions: dict[str, list[str]] = {"handlers": [], "on_connect": ["tokens"]}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_missing_handlers(channels, handler_functions, spec, result)

        # Warning only for bidirectional channel
        assert len(result.warnings) == 1
        assert "coffee" in result.warnings[0]
        assert "tokens" not in result.warnings[0]


class TestCheckOrphanedHandlers:
    """Tests for check_orphaned_handlers function."""

    @staticmethod
    def _create_mock_module(filename: str = "example.py") -> types.ModuleType:
        """Create a mock module with specified filename.

        Args:
            filename: Filename to set for the module (default: example.py)

        Returns:
            Mock ModuleType with __file__ attribute set

        """
        mock_module = types.ModuleType("example")
        mock_module.__file__ = f"/path/to/{filename}"
        return mock_module

    def test_no_orphaned_handlers(self) -> None:
        """Test when all handlers have corresponding channels."""
        channels: dict[str, object] = {"coffee": {}, "chat": {}}
        handler_functions: dict[str, list[str]] = {"handlers": ["coffee", "chat"], "on_connect": ["chat"]}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_orphaned_handlers(channels, handler_functions, self._create_mock_module(), result)

        assert len(result.errors) == 0

    def test_orphaned_handler(self) -> None:
        """Test when a handler has no corresponding channel."""
        channels: dict[str, object] = {"coffee": {}}
        handler_functions: dict[str, list[str]] = {"handlers": ["coffee", "nonexistent"], "on_connect": []}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_orphaned_handlers(channels, handler_functions, self._create_mock_module(), result)

        assert len(result.errors) == 1
        assert "handle_nonexistent" in result.errors[0]
        assert "nonexistent" in result.errors[0]
        assert "example.py" in result.errors[0]

    def test_orphaned_on_connect(self) -> None:
        """Test when an on_connect function has no corresponding channel."""
        channels: dict[str, object] = {"coffee": {}}
        handler_functions: dict[str, list[str]] = {"handlers": ["coffee"], "on_connect": ["coffee", "nonexistent"]}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_orphaned_handlers(channels, handler_functions, self._create_mock_module(), result)

        assert len(result.errors) == 1
        assert "on_connect_nonexistent" in result.errors[0]
        assert "nonexistent" in result.errors[0]
        assert "example.py" in result.errors[0]

    def test_orphaned_both(self) -> None:
        """Test when both handler and on_connect are orphaned."""
        channels: dict[str, object] = {"coffee": {}}
        handler_functions: dict[str, list[str]] = {"handlers": ["coffee", "orphan1"], "on_connect": ["orphan2"]}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_orphaned_handlers(channels, handler_functions, self._create_mock_module("handlers1.py"), result)

        assert len(result.errors) == 2
        assert any("handle_orphan1" in e for e in result.errors)
        assert any("on_connect_orphan2" in e for e in result.errors)
        assert any("handlers1.py" in e for e in result.errors)

    def test_orphaned_handler_multi_module_filename(self) -> None:
        """Test that error messages show correct filename for multi-module components."""
        channels: dict[str, object] = {"coffee": {}}
        handler_functions: dict[str, list[str]] = {"handlers": ["nonexistent"], "on_connect": []}
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        check_orphaned_handlers(channels, handler_functions, self._create_mock_module("handlers2.py"), result)

        assert len(result.errors) == 1
        assert "handlers2.py" in result.errors[0]
        assert "handle_nonexistent" in result.errors[0]


class TestValidateChannelAddresses:
    """Tests for validate_channel_addresses function."""

    def test_valid_addresses(self) -> None:
        """Test channels with valid addresses."""
        channels: dict[str, object] = {
            "coffee": {"address": "/ws/example/v1/coffee"},
            "chat": {"address": "/ws/example/v1/chat"},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        spec: dict[str, Any] = {"servers": {"development": {}}}
        validate_channel_addresses(spec, "example", channels, result)

        assert len(result.errors) == 0

    def test_invalid_component_name(self) -> None:
        """Test channel with wrong component name in address."""
        channels: dict[str, object] = {
            "coffee": {"address": "/ws/example_test/v1/coffee"},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        spec: dict[str, Any] = {"servers": {"development": {}}}
        validate_channel_addresses(spec, "example", channels, result)

        assert len(result.errors) == 1
        assert "coffee" in result.errors[0]
        assert "example_test" in result.errors[0]
        assert "Expected to start with: /ws/example/v1/coffee" in result.errors[0]

    def test_invalid_channel_name(self) -> None:
        """Test channel with wrong channel name in address."""
        channels: dict[str, object] = {
            "coffee": {"address": "/ws/example/v1/tea"},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        spec: dict[str, Any] = {"servers": {"development": {}}}
        validate_channel_addresses(spec, "example", channels, result)

        assert len(result.errors) == 1
        assert "coffee" in result.errors[0]
        assert "Expected to start with: /ws/example/v1/coffee" in result.errors[0]
        assert "Got: /ws/example/v1/tea" in result.errors[0]

    def test_normalized_channel_name(self) -> None:
        """Test channel with kebab-case name uses normalized version in address."""
        channels: dict[str, object] = {
            "agent_events": {"address": "/ws/example/v1/agent_events"},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        spec: dict[str, Any] = {"servers": {"development": {}}}
        validate_channel_addresses(spec, "example", channels, result)

        assert len(result.errors) == 0

    def test_missing_address_field(self) -> None:
        """Test channel without address field."""
        channels: dict[str, object] = {
            "coffee": {},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        spec: dict[str, Any] = {"servers": {"development": {}}}
        validate_channel_addresses(spec, "example", channels, result)

        assert len(result.errors) == 1
        assert "coffee" in result.errors[0]
        assert "missing 'address' field" in result.errors[0]

    def test_empty_address_field(self) -> None:
        """Test channel with empty address field."""
        channels: dict[str, object] = {
            "coffee": {"address": ""},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        spec: dict[str, Any] = {"servers": {"development": {}}}
        validate_channel_addresses(spec, "example", channels, result)

        assert len(result.errors) == 1
        assert "coffee" in result.errors[0]
        assert "missing 'address' field" in result.errors[0]

    def test_multiple_invalid_addresses(self) -> None:
        """Test multiple channels with invalid addresses."""
        channels: dict[str, object] = {
            "coffee": {"address": "/ws/wrong_component/v1/coffee"},
            "chat": {"address": "/ws/example/v1/wrong_channel"},
            "tea": {"address": "/ws/example/v1/tea"},  # Valid
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        spec: dict[str, Any] = {"servers": {"development": {}}}
        validate_channel_addresses(spec, "example", channels, result)

        assert len(result.errors) == 2
        assert any("coffee" in e and "wrong_component" in e for e in result.errors)
        assert any("chat" in e and "wrong_channel" in e for e in result.errors)

    def test_wrong_version(self) -> None:
        """Test channel with wrong version in address."""
        channels: dict[str, object] = {
            "coffee": {"address": "/ws/example/v2/coffee"},
        }
        result = ChannelValidationResult(component_name="example", spec_path="example.yaml")

        spec: dict[str, Any] = {"servers": {"development": {}}}
        validate_channel_addresses(spec, "example", channels, result)

        assert len(result.errors) == 1
        assert "Expected to start with: /ws/example/v1/coffee" in result.errors[0]
        assert "Got: /ws/example/v2/coffee" in result.errors[0]


class TestValidateChannelMappings:
    """Tests for validate_channel_mappings function."""

    def test_valid_mapping(self) -> None:
        """Test validation with valid channel mappings."""
        spec: dict[str, object] = {
            "channels": {
                "coffee": {"address": "/ws/example/v1/coffee"},
                "chat": {"address": "/ws/example/v1/chat"},
            }
        }

        module = types.ModuleType("test_module")

        async def handle_coffee(message: dict[str, object]) -> dict[str, object]:
            return {}

        async def handle_chat(message: dict[str, object]) -> dict[str, object]:
            return {}

        async def on_connect_chat(websocket, connection_id: str) -> None:
            pass

        module.handle_coffee = handle_coffee  # type: ignore[attr-defined]
        module.handle_chat = handle_chat  # type: ignore[attr-defined]
        module.on_connect_chat = on_connect_chat  # type: ignore[attr-defined]

        result = validate_channel_mappings(
            component_name="example", spec=spec, spec_path="example.yaml", handler_module=module
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert result.channels_validated == 2
        assert result.handlers_validated == 3

    def test_missing_handler_warning(self) -> None:
        """Test validation with missing handler."""
        spec: dict[str, object] = {
            "channels": {
                "coffee": {"address": "/ws/example/v1/coffee"},
            }
        }

        module = types.ModuleType("test_module")

        result = validate_channel_mappings(
            component_name="example", spec=spec, spec_path="example.yaml", handler_module=module
        )

        assert result.is_valid is True  # Warnings don't affect validity
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert "handle_coffee" in result.warnings[0]

    def test_orphaned_handler_error(self) -> None:
        """Test validation with orphaned handler."""
        spec: dict[str, object] = {
            "channels": {
                "coffee": {"address": "/ws/example/v1/coffee"},
            }
        }

        module = types.ModuleType("test_module")

        async def handle_coffee(message: dict[str, object]) -> dict[str, object]:
            return {}

        async def handle_orphan(message: dict[str, object]) -> dict[str, object]:
            return {}

        module.handle_coffee = handle_coffee  # type: ignore[attr-defined]
        module.handle_orphan = handle_orphan  # type: ignore[attr-defined]

        result = validate_channel_mappings(
            component_name="example", spec=spec, spec_path="example.yaml", handler_module=module
        )

        assert result.is_valid is False  # Errors affect validity
        assert len(result.errors) == 1
        assert "handle_orphan" in result.errors[0]

    def test_naming_convention_error(self) -> None:
        """Test validation with naming convention violation."""
        spec: dict[str, object] = {
            "channels": {
                "agent-events": {"address": "/ws/example/v1/agent_events"},  # kebab-case (invalid)
            }
        }

        module = types.ModuleType("test_module")

        async def handle_agent_events(message: dict[str, object]) -> dict[str, object]:
            return {}

        module.handle_agent_events = handle_agent_events  # type: ignore[attr-defined]

        result = validate_channel_mappings(
            component_name="example", spec=spec, spec_path="example.yaml", handler_module=module
        )

        assert result.is_valid is False
        assert len(result.errors) >= 1
        # Should have naming convention error
        assert any("agent-events" in e and "snake_case" in e for e in result.errors)

    def test_address_validation_error(self) -> None:
        """Test validation with invalid channel address."""
        spec: dict[str, object] = {
            "channels": {
                "coffee": {"address": "/ws/example_test/v1/coffee"},  # Wrong component name
            }
        }

        module = types.ModuleType("test_module")

        async def handle_coffee(message: dict[str, object]) -> dict[str, object]:
            return {}

        module.handle_coffee = handle_coffee  # type: ignore[attr-defined]

        result = validate_channel_mappings(
            component_name="example", spec=spec, spec_path="example.yaml", handler_module=module
        )

        assert result.is_valid is False
        assert len(result.errors) >= 1
        # Should have address mismatch error
        assert any("address mismatch" in e and "example_test" in e for e in result.errors)

    def test_empty_spec(self) -> None:
        """Test validation with empty spec."""
        spec: dict[str, object] = {"channels": {}}
        module = types.ModuleType("test_module")

        result = validate_channel_mappings(
            component_name="example", spec=spec, spec_path="example.yaml", handler_module=module
        )

        assert result.is_valid is True
        assert len(result.warnings) == 1
        assert "No channels defined" in result.warnings[0]


class TestGetServerPathname:
    """Tests for get_server_pathname function (Phase 1: AAP-58895)."""

    def test_pathname_present(self) -> None:
        """Extract pathname when present in spec."""
        spec = {
            "servers": {
                "development": {
                    "host": "localhost:8000",
                    "protocol": "ws",
                    "pathname": "/api/v1",
                }
            }
        }
        assert get_server_pathname(spec) == "/api/v1"

    def test_pathname_with_trailing_slash(self) -> None:
        """Strip trailing slash from pathname."""
        spec = {"servers": {"development": {"pathname": "/api/v1/"}}}
        assert get_server_pathname(spec) == "/api/v1"

    def test_pathname_missing(self) -> None:
        """Return empty string when pathname field is missing."""
        spec = {"servers": {"development": {"host": "localhost:8000", "protocol": "ws"}}}
        assert get_server_pathname(spec) == ""

    def test_development_server_missing(self) -> None:
        """Return empty string when development server is missing."""
        spec = {"servers": {"production": {"pathname": "/api/v1"}}}
        assert get_server_pathname(spec) == ""

    def test_servers_section_missing(self) -> None:
        """Return empty string when servers section is missing."""
        spec: dict[str, Any] = {"channels": {}}
        assert get_server_pathname(spec) == ""

    def test_malformed_spec_not_dict(self) -> None:
        """Handle malformed spec gracefully.

        These tests intentionally pass invalid types to verify the function
        handles malformed input gracefully by returning an empty string.
        The type: ignore comments are required because we're testing edge cases
        that violate the type contract.
        """
        assert get_server_pathname(None) == ""  # type: ignore[arg-type]  # NOSONAR - intentional type error for testing
        assert get_server_pathname("not a dict") == ""  # type: ignore[arg-type]  # NOSONAR - intentional type error for testing
        assert get_server_pathname([]) == ""  # type: ignore[arg-type]  # NOSONAR - intentional type error for testing

    def test_malformed_servers_section(self) -> None:
        """Handle malformed servers section gracefully."""
        spec = {"servers": "not a dict"}
        assert get_server_pathname(spec) == ""


class TestValidateChannelAddressesWithPathVariables:
    """Tests for validate_channel_addresses with path variables support (Phase 1: AAP-58895)."""

    def test_no_path_variables(self) -> None:
        """Validate channel without path variables (existing behavior)."""
        spec: dict[str, Any] = {
            "servers": {"development": {}},
            "channels": {"invocations": {"address": "/ws/agent_orchestrator/v1/invocations"}},
        }
        result = ChannelValidationResult(component_name="agent_orchestrator", spec_path="test.yaml")
        validate_channel_addresses(spec, "agent_orchestrator", spec["channels"], result)

        assert not result.errors
        assert result.is_valid

    def test_single_path_variable(self) -> None:
        """Validate channel with single path variable (example_schema_agent_orchestrator.yaml)."""
        spec: dict[str, Any] = {
            "servers": {"development": {}},
            "channels": {"invocations": {"address": "/ws/agent_orchestrator/v1/invocations/{invocation_id}"}},
        }
        result = ChannelValidationResult(component_name="agent_orchestrator", spec_path="test.yaml")
        validate_channel_addresses(spec, "agent_orchestrator", spec["channels"], result)

        assert not result.errors
        assert result.is_valid

    def test_multiple_path_variables(self) -> None:
        """Validate channel with multiple path variables."""
        spec: dict[str, Any] = {
            "servers": {"development": {}},
            "channels": {"executions": {"address": "/ws/workflows/v1/executions/{execution_id}/steps/{step_id}"}},
        }
        result = ChannelValidationResult(component_name="workflows", spec_path="test.yaml")
        validate_channel_addresses(spec, "workflows", spec["channels"], result)

        assert not result.errors
        assert result.is_valid

    def test_with_pathname_no_variables(self) -> None:
        """Validate channel with pathname prefix and no path variables."""
        spec = {
            "servers": {"development": {"pathname": "/api/v1"}},
            "channels": {"invocations": {"address": "/api/v1/ws/agent_orchestrator/v1/invocations"}},
        }
        result = ChannelValidationResult(component_name="agent_orchestrator", spec_path="test.yaml")
        validate_channel_addresses(spec, "agent_orchestrator", spec["channels"], result)

        assert not result.errors
        assert result.is_valid

    def test_with_pathname_and_path_variables(self) -> None:
        """Validate channel with both pathname prefix and path variables."""
        spec = {
            "servers": {"development": {"pathname": "/api/v1"}},
            "channels": {"invocations": {"address": "/api/v1/ws/agent_orchestrator/v1/invocations/{invocation_id}"}},
        }
        result = ChannelValidationResult(component_name="agent_orchestrator", spec_path="test.yaml")
        validate_channel_addresses(spec, "agent_orchestrator", spec["channels"], result)

        assert not result.errors
        assert result.is_valid

    def test_wrong_component_name(self) -> None:
        """Validation fails when component name doesn't match."""
        spec: dict[str, Any] = {
            "servers": {"development": {}},
            "channels": {"invocations": {"address": "/ws/wrong_component/v1/invocations/{id}"}},
        }
        result = ChannelValidationResult(component_name="agent_orchestrator", spec_path="test.yaml")
        validate_channel_addresses(spec, "agent_orchestrator", spec["channels"], result)

        assert result.errors
        assert not result.is_valid
        assert any("wrong_component" in e for e in result.errors)

    def test_wrong_base_path(self) -> None:
        """Validation fails when base path is incorrect."""
        spec: dict[str, Any] = {
            "servers": {"development": {}},
            "channels": {"invocations": {"address": "/api/agent_orchestrator/v1/invocations"}},  # Missing /ws/
        }
        result = ChannelValidationResult(component_name="agent_orchestrator", spec_path="test.yaml")
        validate_channel_addresses(spec, "agent_orchestrator", spec["channels"], result)

        assert result.errors
        assert not result.is_valid

    def test_missing_pathname_prefix(self) -> None:
        """Validation fails when pathname is expected but missing from address."""
        spec = {
            "servers": {"development": {"pathname": "/api/v1"}},
            "channels": {
                "invocations": {"address": "/ws/agent_orchestrator/v1/invocations"}  # Missing /api/v1 prefix
            },
        }
        result = ChannelValidationResult(component_name="agent_orchestrator", spec_path="test.yaml")
        validate_channel_addresses(spec, "agent_orchestrator", spec["channels"], result)

        assert result.errors
        assert not result.is_valid
