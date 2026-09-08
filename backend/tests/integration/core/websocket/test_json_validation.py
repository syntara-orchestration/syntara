"""Integration tests for WebSocket JSON validation.

This module tests that WebSocket endpoints properly handle invalid JSON input
by returning appropriate error responses.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from websockets import connect as websocket_connect

from syntara.core.websocket.manager import get_connection_lifecycle_manager


class TestWebSocketJsonValidation:
    """Tests for WebSocket JSON validation error handling."""

    @pytest.mark.asyncio
    async def test_non_json_text_input_chat_endpoint(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that non-JSON text input returns validation error on chat endpoint."""
        _ = example_app_server
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Send non-JSON text
            await websocket.send("asd")

            # Receive error response
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Verify error structure
            assert "error" in response
            assert "message" in response
            assert "timestamp" in response

            # Verify error type
            assert response["error"] == "INVALID_REQUEST"

            # Verify message contains indication of JSON error
            assert "JSON" in response["message"] or "json" in response["message"]

            # Verify timestamp is valid ISO format
            timestamp = datetime.fromisoformat(response["timestamp"])
            assert timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_non_json_text_input_coffee_endpoint(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that non-JSON text input returns validation error on coffee endpoint."""
        _ = example_app_server
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/coffee") as websocket:
            # Send non-JSON text
            await websocket.send("invalid input")

            # Receive error response
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Verify error structure
            assert "error" in response
            assert "message" in response
            assert "timestamp" in response

            # Verify error type
            assert response["error"] == "INVALID_REQUEST"

    @pytest.mark.asyncio
    async def test_malformed_json_missing_quote(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that malformed JSON (missing quote) returns validation error."""
        _ = example_app_server
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Send malformed JSON (missing closing quote)
            await websocket.send('{"message": "hello}')

            # Receive error response
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Verify error structure
            assert "error" in response
            assert response["error"] == "INVALID_REQUEST"
            assert "message" in response
            assert "timestamp" in response

    @pytest.mark.asyncio
    async def test_malformed_json_invalid_structure(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that malformed JSON (invalid structure) returns validation error."""
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Send malformed JSON (invalid structure)
            await websocket.send("{invalid}")

            # Receive error response
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Verify error structure
            assert "error" in response
            assert response["error"] == "INVALID_REQUEST"
            assert "message" in response
            assert "timestamp" in response

    @pytest.mark.asyncio
    async def test_connection_continues_after_json_error(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that WebSocket connection continues after JSON validation error."""
        _ = example_app_server
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Send invalid JSON
            await websocket.send("invalid")

            # Receive error response
            error_response_str = await websocket.recv()
            error_response = json.loads(error_response_str)
            assert error_response["error"] == "INVALID_REQUEST"

            # Connection should still be active - send valid message
            await websocket.send(json.dumps({"message": "hello"}))

            # Should receive valid response (uppercase echo)
            # Note: May also receive random server messages, so we need to filter
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Could be either echo or random message
            assert "reply" in response
            assert "type" in response

            # If it's an echo, verify it
            if response["type"] == "echo":
                assert response["reply"] == "HELLO"

    @pytest.mark.asyncio
    async def test_multiple_json_errors_in_sequence(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that multiple JSON errors can be handled in sequence."""
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Send multiple invalid JSON messages
            for i in range(3):
                await websocket.send(f"invalid{i}")

                # Each should get an error response
                response_str = await websocket.recv()
                response = json.loads(response_str)
                assert response["error"] == "INVALID_REQUEST"
                assert "timestamp" in response

            # Connection should still work with valid message
            await websocket.send(json.dumps({"message": "test"}))
            response_str = await websocket.recv()
            response = json.loads(response_str)
            assert "reply" in response

    @pytest.mark.asyncio
    async def test_empty_string_as_json(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that empty string returns JSON validation error."""
        _ = example_app_server
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Send empty string
            await websocket.send("")

            # Receive error response
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Verify error structure
            assert "error" in response
            assert response["error"] == "INVALID_REQUEST"
            assert "message" in response
            assert "timestamp" in response

    @pytest.mark.asyncio
    async def test_json_error_timestamp_is_recent(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that error timestamp is recent and in correct timezone."""
        _ = example_app_server
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Record time before sending
            before = datetime.now(UTC)

            # Send invalid JSON
            await websocket.send("invalid")

            # Receive error response
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Record time after receiving
            after = datetime.now(UTC)

            # Parse timestamp from response
            error_timestamp = datetime.fromisoformat(response["timestamp"])

            # Verify timestamp is between before and after
            assert before <= error_timestamp <= after

            # Verify timezone is set
            assert error_timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_error_message_contains_useful_information(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that error message contains useful debugging information."""
        _ = example_app_server
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Send invalid JSON
            await websocket.send("{bad json}")

            # Receive error response
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Verify message is not empty and contains useful info
            assert response["message"]
            assert len(response["message"]) > 0

            # Should mention JSON or format issue
            message_lower = response["message"].lower()
            assert any(keyword in message_lower for keyword in ["json", "format", "invalid", "parse", "decode"])

    @pytest.mark.asyncio
    async def test_validation_error_updates_activity_timestamp(self, example_app_server: tuple[Path, FastAPI]) -> None:
        """Test that ValidationError updates the lifecycle manager activity timestamp.

        This verifies that even invalid JSON messages count as connection activity,
        which is correct since receiving data (even malformed) proves the connection is alive.
        """
        _ = example_app_server
        lifecycle_manager = get_connection_lifecycle_manager()

        # Tag this connection with a unique User-Agent so we can identify it
        # server-side among any other "chat" connections.
        user_agent = f"test-{uuid4()}"
        async with websocket_connect(
            "ws://127.0.0.1:9999/ws/testcomp/v1/chat", user_agent_header=user_agent
        ) as websocket:
            # Send valid message first to establish connection
            await websocket.send(json.dumps({"message": "hello"}))
            json.loads(await websocket.recv())

            for _ in range(10):
                # Get connections for the chat channel
                active_connections = [
                    c for c in lifecycle_manager.get_connections_for_channel("chat") if c.user_agent == user_agent
                ]
                if active_connections:
                    conn_info = active_connections[0]
                    break
                await asyncio.sleep(0.2)
            else:
                pytest.fail("Cannot get the new connection from lifecycle_manager")

            # Get the connection for this channel
            initial_activity = conn_info.last_activity_at

            # Wait a bit to ensure timestamp would change
            await asyncio.sleep(0.1)

            # Send invalid JSON to trigger ValidationError
            await websocket.send("invalid json")

            # Receive error response
            error_response_str = await websocket.recv()
            error_response = json.loads(error_response_str)
            assert error_response["error"] == "INVALID_REQUEST"

            # Verify activity timestamp was updated even though message was invalid
            updated_conn_info = lifecycle_manager.get_connection(conn_info.connection_id)
            assert updated_conn_info is not None
            assert updated_conn_info.last_activity_at > initial_activity, (
                "Activity timestamp should be updated when ValidationError occurs, "
                "since receiving any data indicates the connection is alive"
            )
