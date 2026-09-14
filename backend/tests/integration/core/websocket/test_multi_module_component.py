"""Integration tests for components with multiple handler files.

This module tests the full flow of a component split across multiple
handler files (ws/*.py), ensuring:
- File discovery and spec merging
- Channel-to-module mapping in cache
- Validation per module
- WebSocket endpoint creation and execution
"""

from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

from syntara.core.websocket.endpoint_factory import _HANDLER_MODULE_CACHE, scan_handler_specs
from syntara.core.websocket.interceptor import ValidationInterceptor


class TestMultiModuleComponent:
    """Integration tests for multi-module component support."""

    def test_scan_discovers_all_files(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that scan_handler_specs discovers all handler files."""
        _ = example_app_server
        specs = scan_handler_specs()

        assert "testcomp" in specs
        spec = specs["testcomp"]

        # Should have all 3 channels from both files
        assert "channels" in spec
        channels = spec["channels"]
        assert "chat" in channels
        assert "coffee" in channels
        assert "events" in channels

    def test_cache_maps_channels_to_modules(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that _HANDLER_MODULE_CACHE correctly maps channels to their modules."""
        _ = example_app_server
        scan_handler_specs()

        assert "testcomp" in _HANDLER_MODULE_CACHE
        channel_modules = _HANDLER_MODULE_CACHE["testcomp"]

        # All channels should be cached
        assert "chat" in channel_modules
        assert "coffee" in channel_modules
        assert "events" in channel_modules

        # Chat and coffee should share same module (handlers1)
        assert channel_modules["chat"] == channel_modules["coffee"]

        # Events should have different module (handlers2)
        assert channel_modules["events"] != channel_modules["chat"]

        # Module names should be correct
        assert "handlers1" in channel_modules["chat"].__name__
        assert "handlers2" in channel_modules["events"].__name__

    def test_endpoints_created_for_all_channels(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that WebSocket endpoints are created for all channels."""
        _, app = example_app_server

        # Collect paths from top-level routes and included routers
        websocket_paths: set[str] = set()
        for route in app.routes:
            if hasattr(route, "path"):
                websocket_paths.add(route.path)
            if hasattr(route, "original_router"):
                for sub in route.original_router.routes:
                    if hasattr(sub, "path"):
                        websocket_paths.add(sub.path)

        assert "/ws/testcomp/v1/chat" in websocket_paths
        assert "/ws/testcomp/v1/coffee" in websocket_paths
        assert "/ws/testcomp/v1/events" in websocket_paths

    def test_chat_endpoint_uses_handlers1(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that chat endpoint uses handler from handlers1.py."""
        _, app = example_app_server

        with TestClient(app) as client, client.websocket_connect("/ws/testcomp/v1/chat") as websocket:
            # Send chat message
            websocket.send_json({"message": "hello"})

            # Receive response
            response = websocket.receive_json()

            # Verify response from handlers1
            assert response["reply"] == "HELLO"
            assert response["type"] == "echo"
            assert response["handler"] == "handlers1"

    def test_coffee_endpoint_uses_handlers1(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that coffee endpoint uses handler from handlers1.py."""
        _, app = example_app_server

        with TestClient(app) as client, client.websocket_connect("/ws/testcomp/v1/coffee") as websocket:
            # Send coffee request
            websocket.send_json({"input": "hi"})

            # Receive response
            response = websocket.receive_json()

            # Verify response from handlers1
            assert response["output"] == "espresso"
            assert response["handler"] == "handlers1"

    def test_events_endpoint_uses_handlers2(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that events endpoint uses handler from handlers2.py."""
        _, app = example_app_server

        with TestClient(app) as client, client.websocket_connect("/ws/testcomp/v1/events") as websocket:
            # Send events request
            websocket.send_json({"group": "log"})

            # Receive response
            response = websocket.receive_json()

            # Verify response from handlers2
            assert response["status"] == "subscribed"
            assert response["group"] == "log"
            assert response["handler"] == "handlers2"

    def test_validation_succeeds_for_multi_module(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that ValidationInterceptor validates each module correctly."""
        _ = example_app_server
        specs = scan_handler_specs()
        interceptor = ValidationInterceptor()

        # Simulate bootstrap process
        interceptor.on_bootstrap_start(specs)

        # Simulate endpoint creation for each channel (including tokens for receive-only testing)
        for channel_name in ["chat", "coffee", "events", "tokens"]:
            interceptor.before_endpoint_creation("testcomp", channel_name, {})

        # Run validation
        interceptor.on_bootstrap_complete({"total_endpoints": 4})

        # Validation should succeed - verify no errors
        assert len(interceptor.validation_results) > 0
        assert all(result.is_valid for result in interceptor.validation_results)

    def test_all_endpoints_work_concurrently(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that all endpoints from different modules work concurrently."""
        _, app = example_app_server

        with (
            TestClient(app) as client,
            client.websocket_connect("/ws/testcomp/v1/chat") as ws_chat,
            client.websocket_connect("/ws/testcomp/v1/coffee") as ws_coffee,
            client.websocket_connect("/ws/testcomp/v1/events") as ws_events,
        ):
            # Send messages to all endpoints
            ws_chat.send_json({"message": "test"})
            ws_coffee.send_json({"input": "hi"})
            ws_events.send_json({"group": "progress"})

            # Receive responses - order doesn't matter
            chat_resp = ws_chat.receive_json()
            coffee_resp = ws_coffee.receive_json()
            events_resp = ws_events.receive_json()

            # Verify each endpoint used correct handler
            assert chat_resp["handler"] == "handlers1"
            assert coffee_resp["handler"] == "handlers1"
            assert events_resp["handler"] == "handlers2"

            # Verify each response is correct
            assert chat_resp["reply"] == "TEST"
            assert coffee_resp["output"] == "espresso"
            assert events_resp["status"] == "subscribed"
