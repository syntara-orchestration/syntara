"""Tests for WebSocket utility functions."""

from typing import Any

from syntara.core.websocket.utils import is_receive_only_channel, normalize_channel_name


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


class TestIsReceiveOnlyChannel:
    """Tests for is_receive_only_channel function (Phase 1: AAP-58895)."""

    def test_receive_only_channel(self) -> None:
        """Channel with only receive operations is receive-only."""
        spec = {"operations": {"receiveEvents": {"action": "receive", "channel": {"$ref": "#/channels/invocations"}}}}
        assert is_receive_only_channel(spec, "invocations") is True

    def test_send_only_channel(self) -> None:
        """Channel with only send operations is not receive-only."""
        spec = {"operations": {"sendCommands": {"action": "send", "channel": {"$ref": "#/channels/invocations"}}}}
        assert is_receive_only_channel(spec, "invocations") is False

    def test_bidirectional_channel(self) -> None:
        """Channel with both receive and send operations is not receive-only."""
        spec = {
            "operations": {
                "receiveEvents": {"action": "receive", "channel": {"$ref": "#/channels/invocations"}},
                "sendCommands": {"action": "send", "channel": {"$ref": "#/channels/invocations"}},
            }
        }
        assert is_receive_only_channel(spec, "invocations") is False

    def test_no_operations_section(self) -> None:
        """Channel without operations section is assumed bidirectional."""
        spec: dict[str, Any] = {"channels": {"invocations": {}}}
        assert is_receive_only_channel(spec, "invocations") is False

    def test_empty_operations_section(self) -> None:
        """Channel with empty operations section is assumed bidirectional."""
        spec: dict[str, Any] = {"operations": {}}
        assert is_receive_only_channel(spec, "invocations") is False

    def test_multiple_receive_operations(self) -> None:
        """Channel with multiple receive operations is still receive-only."""
        spec = {
            "operations": {
                "receiveEvents": {"action": "receive", "channel": {"$ref": "#/channels/invocations"}},
                "receiveUpdates": {"action": "receive", "channel": {"$ref": "#/channels/invocations"}},
            }
        }
        assert is_receive_only_channel(spec, "invocations") is True

    def test_operation_without_action_field(self) -> None:
        """Operations without action field are ignored."""
        spec = {
            "operations": {
                "malformedOp": {
                    "channel": {"$ref": "#/channels/invocations"}
                    # Missing 'action' field
                },
                "receiveEvents": {"action": "receive", "channel": {"$ref": "#/channels/invocations"}},
            }
        }
        assert is_receive_only_channel(spec, "invocations") is True

    def test_channel_not_in_operations(self) -> None:
        """Channel not referenced in operations is assumed bidirectional."""
        spec = {"operations": {"receiveEvents": {"action": "receive", "channel": {"$ref": "#/channels/other_channel"}}}}
        assert is_receive_only_channel(spec, "invocations") is False

    def test_malformed_operations(self) -> None:
        """Malformed operations section is handled gracefully."""
        spec = {"operations": "not a dict"}
        assert is_receive_only_channel(spec, "invocations") is False

    def test_malformed_operation_entry(self) -> None:
        """Malformed operation entry is handled gracefully."""
        spec = {
            "operations": {
                "bad_operation": "not a dict",
                "receiveEvents": {"action": "receive", "channel": {"$ref": "#/channels/invocations"}},
            }
        }
        assert is_receive_only_channel(spec, "invocations") is True
