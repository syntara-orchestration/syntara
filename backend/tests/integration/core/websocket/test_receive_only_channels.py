"""Integration tests for receive-only WebSocket channels (Phase 3: AAP-58895).

Receive-only channels are tested with real WebSocket clients (websockets library) because
Starlette's TestClient has race conditions with message queues in receive-only mode.

Bidirectional channels continue using TestClient for consistency with existing tests.
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from websockets import connect as websocket_connect


class TestReceiveOnlyChannelIntegration:
    """Integration tests for receive-only channel behavior."""

    @pytest.mark.asyncio
    async def test_receive_only_channel_sends_events_via_on_connect(
        self, example_app_server: tuple[Path, FastAPI]
    ) -> None:
        """Events sent through on_connect handler."""
        _ = example_app_server
        # Connect to receive-only tokens channel with real WebSocket client
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/tokens") as websocket:
            # Receive first token (no send required)
            token0_str = await websocket.recv()
            token0 = json.loads(token0_str)
            assert "token" in token0
            assert "sequence" in token0
            assert token0["token"] == "token_0"  # noqa: S105
            assert token0["sequence"] == 0

            # Receive second token
            token1_str = await websocket.recv()
            token1 = json.loads(token1_str)
            assert token1["token"] == "token_1"  # noqa: S105
            assert token1["sequence"] == 1

            # Receive third token
            token2_str = await websocket.recv()
            token2 = json.loads(token2_str)
            assert token2["token"] == "token_2"  # noqa: S105
            assert token2["sequence"] == 2

            # Verify timestamp is present
            assert "timestamp" in token2

    @pytest.mark.asyncio
    async def test_receive_only_channel_stays_alive_until_disconnect(
        self, example_app_server: tuple[Path, FastAPI]
    ) -> None:
        """Connection maintained until all messages sent."""
        _ = example_app_server
        # Connect to receive-only tokens channel
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/tokens") as websocket:
            # Receive all 5 tokens sent by on_connect
            tokens_received = []
            for i in range(5):
                token_str = await websocket.recv()
                token = json.loads(token_str)
                tokens_received.append(token)
                assert token["token"] == f"token_{i}"
                assert token["sequence"] == i

            # Verify all 5 tokens received successfully
            assert len(tokens_received) == 5

    @pytest.mark.asyncio
    async def test_bidirectional_channel_still_requires_handler(self, example_app_server: tuple[Path, FastAPI]) -> None:
        _ = example_app_server
        """Existing behavior unchanged (regression)."""
        # Connect to bidirectional chat channel using real WebSocket client
        async with websocket_connect("ws://127.0.0.1:9999/ws/testcomp/v1/chat") as websocket:
            # Send chat message (bidirectional)
            await websocket.send(json.dumps({"message": "hello there"}))

            # Receive response (may also receive random messages)
            response_str = await websocket.recv()
            response = json.loads(response_str)

            # Should receive a response with reply and type
            assert "reply" in response
            assert "type" in response

            # If it's an echo, verify it's uppercase
            if response["type"] == "echo":
                assert response["reply"] == "HELLO THERE"

            # Verify timestamp is present
            assert "timestamp" in response
