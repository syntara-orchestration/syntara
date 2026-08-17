"""Tests for WebSocket endpoint factory with automatic path mapping discovery."""

import asyncio
import json
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.core.websocket.endpoint_factory import (
    _HANDLER_MODULE_CACHE,
    _SPEC_CACHE,
    _check_websocket_authorization,
    create_websocket_endpoint,
    scan_handler_specs,
)


def _create_mock_traversable(path: Path) -> Mock:
    """Create a mock Traversable object for importlib.resources.

    Args:
        path: Path to wrap in a mock Traversable

    Returns:
        Mock object that behaves like a Traversable

    """
    mock = Mock()
    mock.is_file.return_value = path.is_file()
    mock.is_dir.return_value = path.is_dir()
    mock.read_text.return_value = path.read_text() if path.is_file() else ""
    mock.name = path.name
    mock.suffix = path.suffix

    # Use configure_mock for magic methods (lambda must accept self)
    mock.configure_mock(__str__=lambda self: str(path), __fspath__=lambda self: str(path))  # noqa: ARG005

    def joinpath(*parts: str) -> Mock:
        new_path = path.joinpath(*parts)
        return _create_mock_traversable(new_path)

    def iterdir() -> list[Mock]:
        if path.is_dir():
            return [_create_mock_traversable(p) for p in path.iterdir()]
        return []

    mock.joinpath = joinpath
    mock.iterdir = iterdir

    return mock


def _create_mock_files_function(syntara_dir: Path) -> object:
    """Create a mock files() function for tests.

    Args:
        syntara_dir: Path to the test syntara directory

    Returns:
        Mock function that returns traversable for syntara package

    """

    def mock_files(package: str) -> Mock:
        if package == "syntara":
            return _create_mock_traversable(syntara_dir)
        msg = f"Package {package} not found"
        raise FileNotFoundError(msg)

    return mock_files


class TestAutomaticPathMapping:
    """Test automatic handler-to-spec path mapping discovery."""

    def test_handler_with_matching_spec(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Handler file with matching spec file is discovered successfully."""
        # Create directory structure
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"
        component_dir = syntara_dir / "test_component"
        ws_dir = component_dir / "ws"
        ws_dir.mkdir(parents=True)

        # Create spec file following convention: websocket-{handler}.yaml
        schemas_dir = tmp_path / "src" / "syntara" / "schemas" / "test_component"
        schemas_dir.mkdir(parents=True)
        spec_file = schemas_dir / "websocket-example.yaml"
        spec_file.write_text("asyncapi: 3.0.0\nchannels: {}\n")

        # Create handler file: example.py (maps to websocket-example.yaml)
        handler_file = ws_dir / "example.py"
        handler_file.write_text("# Handler file\n")

        # Monkeypatch __file__ and files() function
        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Mock importlib.resources.files to return our temp directory
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", _create_mock_files_function(syntara_dir))

        result = scan_handler_specs()

        assert "test_component" in result
        assert isinstance(result["test_component"], dict)
        assert "asyncapi" in result["test_component"]

    def test_handler_without_spec_raises_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Handler file without corresponding spec file raises SafeValueError."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"
        component_dir = syntara_dir / "test_component"
        ws_dir = component_dir / "ws"
        ws_dir.mkdir(parents=True)

        # Create schemas dir but no spec file
        schemas_dir = tmp_path / "src" / "syntara" / "schemas" / "test_component"
        schemas_dir.mkdir(parents=True)

        # Create handler file WITHOUT matching spec
        handler_file = ws_dir / "orphan_handler.py"
        handler_file.write_text("# Handler without spec\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Mock importlib.resources.files
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", _create_mock_files_function(syntara_dir))

        with pytest.raises(SafeValueError, match="Missing Spec File"):
            scan_handler_specs()

    def test_spec_without_handler_raises_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Spec file without corresponding handler file raises SafeValueError."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"
        component_dir = syntara_dir / "test_component"
        ws_dir = component_dir / "ws"
        ws_dir.mkdir(parents=True)

        # Create orphan spec file (no matching handler)
        schemas_dir = tmp_path / "src" / "syntara" / "schemas" / "test_component"
        schemas_dir.mkdir(parents=True)
        spec_file = schemas_dir / "websocket-orphan.yaml"
        spec_file.write_text("asyncapi: 3.0.0\nchannels: {}\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Mock importlib.resources.files
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", _create_mock_files_function(syntara_dir))

        with pytest.raises(SafeValueError, match="Orphan Spec File"):
            scan_handler_specs()

    def test_component_without_ws_dir_skips_orphan_check(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Components without ws/ directory don't trigger orphan spec errors."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"

        # Create a component WITHOUT ws/ directory
        component_dir = syntara_dir / "no_ws_component"
        component_dir.mkdir(parents=True)

        # Create spec file for component without ws/ (should be ignored)
        schemas_dir = tmp_path / "schemas" / "no_ws_component"
        schemas_dir.mkdir(parents=True)
        spec_file = schemas_dir / "websocket-example.yaml"
        spec_file.write_text("asyncapi: 3.0.0\nchannels: {}\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Should not raise error - component without ws/ is skipped
        result = scan_handler_specs()
        assert "no_ws_component" not in result

    def test_multiple_handlers_with_matching_specs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple handlers in ws/ directory with matching specs are discovered."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"
        component_dir = syntara_dir / "multi_handler"
        ws_dir = component_dir / "ws"
        ws_dir.mkdir(parents=True)

        schemas_dir = tmp_path / "src" / "syntara" / "schemas" / "multi_handler"
        schemas_dir.mkdir(parents=True)

        # Create multiple handler/spec pairs
        handlers = ["chat", "coffee", "events"]
        for handler_name in handlers:
            handler_file = ws_dir / f"{handler_name}.py"
            handler_file.write_text(f"# Handler for {handler_name}\n")

            spec_file = schemas_dir / f"websocket-{handler_name}.yaml"
            spec_file.write_text(f"asyncapi: 3.0.0\nchannels:\n  {handler_name}:\n    address: /ws/{handler_name}\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Mock importlib.resources.files
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", _create_mock_files_function(syntara_dir))

        result = scan_handler_specs()

        assert "multi_handler" in result
        # All handlers should contribute channels to the merged spec
        assert "channels" in result["multi_handler"]

    def test_supports_yaml_and_yml_extensions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Automatic mapping supports both .yaml and .yml extensions."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"

        # Test .yml extension
        component_dir = syntara_dir / "yml_component"
        ws_dir = component_dir / "ws"
        ws_dir.mkdir(parents=True)

        schemas_dir = tmp_path / "src" / "syntara" / "schemas" / "yml_component"
        schemas_dir.mkdir(parents=True)
        spec_file = schemas_dir / "websocket-test.yml"  # .yml extension
        spec_file.write_text("asyncapi: 3.0.0\nchannels: {}\n")

        handler_file = ws_dir / "test.py"
        handler_file.write_text("# Handler\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Mock importlib.resources.files
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", _create_mock_files_function(syntara_dir))

        result = scan_handler_specs()

        assert "yml_component" in result
        assert "asyncapi" in result["yml_component"]

    def test_supports_json_extension(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Automatic mapping supports .json extension for AsyncAPI specs with full parsing."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"

        # Test .json extension with a complete AsyncAPI spec
        component_dir = syntara_dir / "json_component"
        ws_dir = component_dir / "ws"
        ws_dir.mkdir(parents=True)

        schemas_dir = tmp_path / "src" / "syntara" / "schemas" / "json_component"
        schemas_dir.mkdir(parents=True)

        # Create a complete JSON AsyncAPI spec with channels, messages, and operations
        json_spec = {
            "asyncapi": "3.0.0",
            "info": {
                "title": "JSON Test API",
                "version": "1.0.0",
                "description": "Test AsyncAPI spec in JSON format",
            },
            "channels": {
                "test_channel": {
                    "address": "/ws/json_component/v1/test_channel",
                    "messages": {
                        "testRequest": {"$ref": "#/components/messages/TestRequest"},
                        "testResponse": {"$ref": "#/components/messages/TestResponse"},
                    },
                }
            },
            "operations": {
                "sendTestRequest": {
                    "action": "send",
                    "channel": {"$ref": "#/channels/test_channel"},
                    "messages": [{"$ref": "#/channels/test_channel/messages/testRequest"}],
                },
                "receiveTestResponse": {
                    "action": "receive",
                    "channel": {"$ref": "#/channels/test_channel"},
                    "messages": [{"$ref": "#/channels/test_channel/messages/testResponse"}],
                },
            },
            "components": {
                "messages": {
                    "TestRequest": {
                        "name": "TestRequest",
                        "contentType": "application/json",
                        "payload": {
                            "type": "object",
                            "required": ["input"],
                            "properties": {"input": {"type": "string"}},
                        },
                    },
                    "TestResponse": {
                        "name": "TestResponse",
                        "contentType": "application/json",
                        "payload": {
                            "type": "object",
                            "required": ["output"],
                            "properties": {"output": {"type": "string"}},
                        },
                    },
                }
            },
        }

        spec_file = schemas_dir / "websocket-test.json"
        spec_file.write_text(json.dumps(json_spec, indent=2))

        handler_file = ws_dir / "test.py"
        handler_file.write_text("# Handler for JSON spec\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Mock importlib.resources.files
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", _create_mock_files_function(syntara_dir))

        result = scan_handler_specs()

        # Verify the component was discovered
        assert "json_component" in result

        # Verify the spec was parsed correctly
        spec = result["json_component"]
        assert spec["asyncapi"] == "3.0.0"
        assert spec["info"]["title"] == "JSON Test API"
        assert spec["info"]["version"] == "1.0.0"

        # Verify channels were parsed
        assert "channels" in spec
        assert "test_channel" in spec["channels"]
        assert spec["channels"]["test_channel"]["address"] == "/ws/json_component/v1/test_channel"

        # Verify operations were parsed
        assert "operations" in spec
        assert "sendTestRequest" in spec["operations"]
        assert "receiveTestResponse" in spec["operations"]

        # Verify components/messages were parsed
        assert "components" in spec
        assert "messages" in spec["components"]
        assert "TestRequest" in spec["components"]["messages"]
        assert "TestResponse" in spec["components"]["messages"]

        # Verify message payload structure
        test_request = spec["components"]["messages"]["TestRequest"]
        assert test_request["payload"]["type"] == "object"
        assert "input" in test_request["payload"]["properties"]

    def test_skips_init_py_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """__init__.py files in ws/ directory are skipped."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"
        component_dir = syntara_dir / "test_component"
        ws_dir = component_dir / "ws"
        ws_dir.mkdir(parents=True)

        # Create __init__.py (should be skipped, no matching spec needed)
        init_file = ws_dir / "__init__.py"
        init_file.write_text("# Init file\n")

        # Create actual handler with matching spec
        handler_file = ws_dir / "example.py"
        handler_file.write_text("# Handler\n")

        schemas_dir = tmp_path / "src" / "syntara" / "schemas" / "test_component"
        schemas_dir.mkdir(parents=True)
        spec_file = schemas_dir / "websocket-example.yaml"
        spec_file.write_text("asyncapi: 3.0.0\nchannels: {}\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Mock importlib.resources.files
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", _create_mock_files_function(syntara_dir))

        # Should not fail even though __init__.py has no matching spec
        result = scan_handler_specs()
        assert "test_component" in result

    def test_skips_special_directories(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Skips __pycache__, core, api directories."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"

        # Create special directories that should be skipped
        for dir_name in ["__pycache__", "core", "api"]:
            special_dir = syntara_dir / dir_name
            ws_dir = special_dir / "ws"
            ws_dir.mkdir(parents=True)
            handler_file = ws_dir / "test.py"
            handler_file.write_text("# Should be skipped\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        result = scan_handler_specs()

        # Special directories should not appear in results
        for dir_name in ["__pycache__", "core", "api"]:
            assert dir_name not in result

    def test_handler_import_error_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Handler with import error is skipped (but spec must exist)."""
        core_websocket_dir = tmp_path / "src" / "syntara" / "core" / "websocket"
        core_websocket_dir.mkdir(parents=True)

        syntara_dir = tmp_path / "src" / "syntara"
        component_dir = syntara_dir / "test_component"
        ws_dir = component_dir / "ws"
        ws_dir.mkdir(parents=True)

        # Create handler with import error
        handler_file = ws_dir / "broken.py"
        handler_file.write_text("import nonexistent_module\n")

        # Create matching spec file (required for the handler)
        schemas_dir = tmp_path / "src" / "syntara" / "schemas" / "test_component"
        schemas_dir.mkdir(parents=True)
        spec_file = schemas_dir / "websocket-broken.yaml"
        spec_file.write_text("asyncapi: 3.0.0\nchannels: {}\n")

        fake_file = core_websocket_dir / "endpoint_factory.py"
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory._get_module_file", lambda: str(fake_file))

        # Mock importlib.resources.files
        monkeypatch.setattr("syntara.core.websocket.endpoint_factory.files", _create_mock_files_function(syntara_dir))

        # Handler with import error is skipped (doesn't fail startup)
        result = scan_handler_specs()
        # Component is skipped because module failed to load
        assert "test_component" not in result


def _create_mock_handler_module(
    channel_name: str = "test",
    *,
    has_handler: bool = True,
    has_on_connect: bool = False,
) -> types.ModuleType:
    """Create a mock handler module for testing.

    Args:
        channel_name: Name of the channel (for function naming)
        has_handler: Whether to include handle_{channel} function
        has_on_connect: Whether to include on_connect_{channel} function

    Returns:
        Mock module with specified functions

    """
    module = types.ModuleType("mock_handler")

    if has_handler:

        async def handle_test(_message: dict[str, Any]) -> dict[str, Any]:
            """Mock message handler for testing endpoint creation."""
            await asyncio.sleep(0)  # Yield control to event loop
            return {"status": "ok"}

        setattr(module, f"handle_{channel_name}", handle_test)

    if has_on_connect:

        async def on_connect_test(_websocket: object, _connection_id: str) -> None:
            """Mock on_connect handler for testing endpoint creation."""
            await asyncio.sleep(0)  # Yield control to event loop

        setattr(module, f"on_connect_{channel_name}", on_connect_test)

    return module


def _create_receive_only_spec(channel_name: str = "test") -> dict[str, Any]:
    """Create a receive-only channel spec (no Request message, only send operation).

    Args:
        channel_name: Name of the channel

    Returns:
        AsyncAPI spec dictionary

    """
    return {
        "asyncapi": "3.0.0",
        "channels": {
            channel_name: {
                "address": f"/ws/{channel_name}",
                "messages": {"TestEvent": {"$ref": "#/components/messages/TestEvent"}},
            }
        },
        "operations": {
            f"send{channel_name.title()}": {"action": "send", "channel": {"$ref": f"#/channels/{channel_name}"}}
        },
        "components": {"messages": {"TestEvent": {"payload": {"type": "object"}}}},
    }


def _create_bidirectional_spec(
    channel_name: str = "test",
    *,
    has_request_message: bool = True,
) -> dict[str, Any]:
    """Create a bidirectional channel spec.

    Args:
        channel_name: Name of the channel
        has_request_message: Whether to include *Request message

    Returns:
        AsyncAPI spec dictionary

    """
    messages: dict[str, Any] = {}
    if has_request_message:
        messages["TestRequest"] = {"$ref": "#/components/messages/TestRequest"}
    messages["TestResponse"] = {"$ref": "#/components/messages/TestResponse"}

    return {
        "asyncapi": "3.0.0",
        "channels": {channel_name: {"address": f"/ws/{channel_name}", "messages": messages}},
        "operations": {
            f"receive{channel_name.title()}": {"action": "receive", "channel": {"$ref": f"#/channels/{channel_name}"}},
            f"send{channel_name.title()}": {"action": "send", "channel": {"$ref": f"#/channels/{channel_name}"}},
        },
        "components": {
            "messages": {
                "TestRequest": {"payload": {"type": "object"}},
                "TestResponse": {"payload": {"type": "object"}},
            }
        },
    }


class TestReceiveOnlyChannels:
    """Tests for receive-only channel support (Phase 3: AAP-58895)."""

    @patch(
        "syntara.core.websocket.endpoint_factory._HANDLER_MODULE_CACHE",
        {"test_component": {"test": _create_mock_handler_module(has_handler=False, has_on_connect=True)}},
    )
    @patch("syntara.core.websocket.endpoint_factory.discover_hooks")
    @patch("syntara.core.websocket.endpoint_factory.is_receive_only_channel")
    def test_receive_only_no_request_message_allowed(
        self,
        mock_is_receive_only: MagicMock,
        mock_discover_hooks: MagicMock,
    ) -> None:
        """Receive-only channel without Request message doesn't raise SafeValueError."""
        mock_is_receive_only.return_value = True
        mock_discover_hooks.return_value = MagicMock()

        spec = _create_receive_only_spec()

        # Should not raise SafeValueError even without Request message
        endpoint = create_websocket_endpoint("test", spec, "test_component")
        assert callable(endpoint)

    @patch(
        "syntara.core.websocket.endpoint_factory._HANDLER_MODULE_CACHE",
        {"test_component": {"test": _create_mock_handler_module(has_handler=False, has_on_connect=True)}},
    )
    @patch("syntara.core.websocket.endpoint_factory.discover_hooks")
    @patch("syntara.core.websocket.endpoint_factory.is_receive_only_channel")
    def test_receive_only_no_handler_function_allowed(
        self,
        mock_is_receive_only: MagicMock,
        mock_discover_hooks: MagicMock,
    ) -> None:
        """Receive-only channel without handle_xxx doesn't raise error."""
        mock_is_receive_only.return_value = True
        mock_discover_hooks.return_value = MagicMock()

        spec = _create_receive_only_spec()

        # Should not raise SafeValueError even without handle_test function
        endpoint = create_websocket_endpoint("test", spec, "test_component")
        assert callable(endpoint)

    @patch(
        "syntara.core.websocket.endpoint_factory._HANDLER_MODULE_CACHE",
        {"test_component": {"test": _create_mock_handler_module(has_handler=False, has_on_connect=False)}},
    )
    @patch("syntara.core.websocket.endpoint_factory.discover_hooks")
    @patch("syntara.core.websocket.endpoint_factory.is_receive_only_channel")
    def test_receive_only_requires_on_connect(
        self,
        mock_is_receive_only: MagicMock,
        mock_discover_hooks: MagicMock,
    ) -> None:
        """Receive-only channel without on_connect raises SafeValueError at runtime.

        Note: The SafeValueError is raised at runtime when the endpoint is called,
        not at endpoint creation time. This test verifies the endpoint is created
        but will fail at runtime.
        """
        mock_is_receive_only.return_value = True
        mock_discover_hooks.return_value = MagicMock()

        spec = _create_receive_only_spec()

        # Endpoint creation succeeds - the check happens at runtime
        endpoint = create_websocket_endpoint("test", spec, "test_component")
        assert callable(endpoint)

    @patch(
        "syntara.core.websocket.endpoint_factory._HANDLER_MODULE_CACHE",
        {"test_component": {"test": _create_mock_handler_module(has_handler=True)}},
    )
    @patch("syntara.core.websocket.endpoint_factory.discover_hooks")
    @patch("syntara.core.websocket.endpoint_factory.is_receive_only_channel")
    def test_bidirectional_requires_request_message(
        self,
        mock_is_receive_only: MagicMock,
        mock_discover_hooks: MagicMock,
    ) -> None:
        """Bidirectional channel must have Request message (regression)."""
        mock_is_receive_only.return_value = False
        mock_discover_hooks.return_value = MagicMock()

        # Create spec WITHOUT Request message
        spec = _create_bidirectional_spec(has_request_message=False)

        # Should raise SafeValueError for bidirectional channel without Request
        with pytest.raises(SafeValueError, match="No request message type found"):
            create_websocket_endpoint("test", spec, "test_component")

    @patch(
        "syntara.core.websocket.endpoint_factory._HANDLER_MODULE_CACHE",
        {"test_component": {"test": _create_mock_handler_module(has_handler=False)}},
    )
    @patch("syntara.core.websocket.endpoint_factory.discover_hooks")
    @patch("syntara.core.websocket.endpoint_factory.is_receive_only_channel")
    def test_bidirectional_requires_handler_function(
        self,
        mock_is_receive_only: MagicMock,
        mock_discover_hooks: MagicMock,
    ) -> None:
        """Bidirectional channel must have handle_xxx (regression)."""
        mock_is_receive_only.return_value = False
        mock_discover_hooks.return_value = MagicMock()

        spec = _create_bidirectional_spec(has_request_message=True)

        # Should raise SafeValueError for bidirectional channel without handler
        with pytest.raises(SafeValueError, match=r"Handler function .* not found"):
            create_websocket_endpoint("test", spec, "test_component")


class TestCacheClearing:
    """Tests for cache management in scan_handler_specs."""

    def test_scan_handler_specs_clears_caches(self) -> None:
        """Test that scan_handler_specs() clears global caches on each call."""
        # Pollute the caches with stale data
        _SPEC_CACHE["stale_component"] = {"channels": {}}
        _HANDLER_MODULE_CACHE["stale_component"] = {"stale_channel": types.ModuleType("stale")}

        # Verify caches are polluted
        assert "stale_component" in _SPEC_CACHE
        assert "stale_component" in _HANDLER_MODULE_CACHE

        # Call scan_handler_specs - should clear caches
        # Note: This will scan actual codebase, but that's fine for this test
        scan_handler_specs()

        # Verify caches were cleared and repopulated with only real data
        assert "stale_component" not in _SPEC_CACHE
        assert "stale_component" not in _HANDLER_MODULE_CACHE

    def test_multiple_scan_calls_are_idempotent(self) -> None:
        """Test that calling scan_handler_specs() multiple times produces consistent results."""
        # First scan
        result1 = scan_handler_specs()

        # Second scan
        result2 = scan_handler_specs()

        # Results should be identical (same components, same channels)
        assert result1.keys() == result2.keys()
        for component_name in result1:
            channels1 = result1[component_name].get("channels", {})
            channels2 = result2[component_name].get("channels", {})
            assert channels1.keys() == channels2.keys()


def _make_ws(component: str, resource_id: str) -> MagicMock:
    """Create a mock WebSocket with path_params and app.state.authz_evaluator."""
    ws = MagicMock()
    param_map = {"workflows": "execution_id", "agent_orchestrator": "invocation_id"}
    param_name = param_map.get(component, "id")
    ws.path_params = {param_name: resource_id}
    ws.app.state.authz_evaluator = MagicMock()
    return ws


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    return user


_PATCH_SESSION = "syntara.core.websocket.endpoint_factory.AsyncSessionLocal"
_PATCH_AUTHORIZE = "syntara.core.websocket.endpoint_factory.authorize"


def _mock_session_factory(mock_db: AsyncMock) -> MagicMock:
    """Create a session factory mock that works as an async context manager."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


class TestCheckWebSocketAuthorization:
    """Unit tests for _check_websocket_authorization project resolution."""

    @pytest.mark.asyncio
    async def test_execution_resolves_project_name(self) -> None:
        execution_id = str(uuid4())
        ws = _make_ws("workflows", execution_id)
        user = _make_user()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "MyProject"
        mock_db.execute.return_value = mock_result

        mock_authz_result = MagicMock(allowed=True, denied=False)

        with (
            patch(_PATCH_SESSION, _mock_session_factory(mock_db)),
            patch(_PATCH_AUTHORIZE, AsyncMock(return_value=mock_authz_result)) as mock_authorize,
        ):
            result = await _check_websocket_authorization(ws, user, "test-channel", "workflows")

        assert result is True
        authz_request = mock_authorize.call_args[0][2]
        assert authz_request.resource_project == "MyProject"
        assert authz_request.resource_type == "execution"

    @pytest.mark.asyncio
    async def test_invocation_resolves_project_name(self) -> None:
        invocation_id = str(uuid4())
        ws = _make_ws("agent_orchestrator", invocation_id)
        user = _make_user()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "AgentProject"
        mock_db.execute.return_value = mock_result

        mock_authz_result = MagicMock(allowed=True, denied=False)

        with (
            patch(_PATCH_SESSION, _mock_session_factory(mock_db)),
            patch(_PATCH_AUTHORIZE, AsyncMock(return_value=mock_authz_result)) as mock_authorize,
        ):
            result = await _check_websocket_authorization(ws, user, "test-channel", "agent_orchestrator")

        assert result is True
        authz_request = mock_authorize.call_args[0][2]
        assert authz_request.resource_project == "AgentProject"
        assert authz_request.resource_type == "invocation"

    @pytest.mark.asyncio
    async def test_unknown_resource_type_returns_false(self) -> None:
        resource_id = str(uuid4())
        ws = MagicMock()
        ws.path_params = {"task_id": resource_id}
        ws.app.state.authz_evaluator = MagicMock()
        user = _make_user()

        mock_db = AsyncMock()
        with (
            patch(
                "syntara.core.websocket.endpoint_factory._COMPONENT_RESOURCE_PARAM_MAP",
                {"tasks": "task_id"},
            ),
            patch(_PATCH_SESSION, _mock_session_factory(mock_db)),
        ):
            result = await _check_websocket_authorization(ws, user, "test-channel", "tasks")

        assert result is False

    @pytest.mark.asyncio
    async def test_missing_resource_id_returns_false(self) -> None:
        ws = MagicMock()
        ws.path_params = {}
        user = _make_user()

        result = await _check_websocket_authorization(ws, user, "test-channel", "workflows")

        assert result is False

    @pytest.mark.asyncio
    async def test_unmapped_component_returns_false(self) -> None:
        ws = _make_ws("unknown_component", str(uuid4()))
        ws.path_params = {"id": str(uuid4())}
        user = _make_user()

        result = await _check_websocket_authorization(ws, user, "test-channel", "unknown_component")

        assert result is False

    @pytest.mark.asyncio
    async def test_resource_not_found_returns_false(self) -> None:
        execution_id = str(uuid4())
        ws = _make_ws("workflows", execution_id)
        user = _make_user()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch(_PATCH_SESSION, _mock_session_factory(mock_db)):
            result = await _check_websocket_authorization(ws, user, "test-channel", "workflows")

        assert result is False

    @pytest.mark.asyncio
    async def test_authorization_denied_returns_false(self) -> None:
        execution_id = str(uuid4())
        ws = _make_ws("workflows", execution_id)
        user = _make_user()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "SomeProject"
        mock_db.execute.return_value = mock_result

        mock_authz_result = MagicMock(allowed=False, denied=True)

        with (
            patch(_PATCH_SESSION, _mock_session_factory(mock_db)),
            patch(_PATCH_AUTHORIZE, AsyncMock(return_value=mock_authz_result)),
        ):
            result = await _check_websocket_authorization(ws, user, "test-channel", "workflows")

        assert result is False

    @pytest.mark.asyncio
    async def test_db_exception_returns_false(self) -> None:
        execution_id = str(uuid4())
        ws = _make_ws("workflows", execution_id)
        user = _make_user()

        with patch(_PATCH_SESSION, side_effect=RuntimeError("DB connection failed")):
            result = await _check_websocket_authorization(ws, user, "test-channel", "workflows")

        assert result is False
