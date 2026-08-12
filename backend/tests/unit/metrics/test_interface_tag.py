"""Unit tests for API-vs-UI interface detection.

Tests cover the ``detect_interface`` function and the ``interface_context_var``
ContextVar used to propagate the detected interface through the request lifecycle.
"""

from __future__ import annotations

from typing import Any

import pytest

from syntara.metrics.interface_tag import (
    INTERFACE_API,
    INTERFACE_HEADER,
    INTERFACE_UI,
    detect_interface,
    interface_context_var,
)


def _make_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    """Build a minimal ASGI scope with the given headers."""
    return {
        "type": "http",
        "path": "/api/v1/workflows",
        "method": "GET",
        "headers": headers or [],
    }


class TestDetectInterface:
    """Tests for detect_interface header inspection."""

    def test_ui_header_present(self) -> None:
        """Request with X-Orchestrator-Client: ui is classified as UI."""
        scope = _make_scope(headers=[(b"x-orchestrator-client", b"ui")])
        assert detect_interface(scope) == INTERFACE_UI

    def test_no_header_defaults_to_api(self) -> None:
        """Request without X-Orchestrator-Client header defaults to API."""
        scope = _make_scope(headers=[])
        assert detect_interface(scope) == INTERFACE_API

    def test_empty_headers_defaults_to_api(self) -> None:
        """Scope with no headers key still returns API."""
        scope: dict[str, Any] = {"type": "http", "path": "/", "method": "GET"}
        assert detect_interface(scope) == INTERFACE_API

    def test_header_value_case_insensitive(self) -> None:
        """Header value matching is case-insensitive."""
        scope = _make_scope(headers=[(b"x-orchestrator-client", b"UI")])
        assert detect_interface(scope) == INTERFACE_UI

        scope = _make_scope(headers=[(b"x-orchestrator-client", b"Ui")])
        assert detect_interface(scope) == INTERFACE_UI

    def test_header_name_case_insensitive(self) -> None:
        """Header name matching is case-insensitive per HTTP spec."""
        scope = _make_scope(headers=[(b"X-Orchestrator-Client", b"ui")])
        assert detect_interface(scope) == INTERFACE_UI

        scope = _make_scope(headers=[(b"X-ORCHESTRATOR-CLIENT", b"ui")])
        assert detect_interface(scope) == INTERFACE_UI

    def test_header_value_with_whitespace(self) -> None:
        """Whitespace around the header value is stripped."""
        scope = _make_scope(headers=[(b"x-orchestrator-client", b"  ui  ")])
        assert detect_interface(scope) == INTERFACE_UI

    def test_unknown_header_value_classified_as_api(self) -> None:
        """Unrecognized X-Orchestrator-Client values default to API."""
        scope = _make_scope(headers=[(b"x-orchestrator-client", b"cli")])
        assert detect_interface(scope) == INTERFACE_API

        scope = _make_scope(headers=[(b"x-orchestrator-client", b"unknown")])
        assert detect_interface(scope) == INTERFACE_API

    def test_empty_header_value_classified_as_api(self) -> None:
        """Empty X-Orchestrator-Client value defaults to API."""
        scope = _make_scope(headers=[(b"x-orchestrator-client", b"")])
        assert detect_interface(scope) == INTERFACE_API

    def test_other_headers_ignored(self) -> None:
        """Non-matching headers do not affect detection."""
        scope = _make_scope(
            headers=[
                (b"authorization", b"Bearer token123"),
                (b"content-type", b"application/json"),
            ]
        )
        assert detect_interface(scope) == INTERFACE_API

    def test_ui_header_among_other_headers(self) -> None:
        """UI header is detected even when mixed with other headers."""
        scope = _make_scope(
            headers=[
                (b"authorization", b"Bearer token123"),
                (b"x-orchestrator-client", b"ui"),
                (b"content-type", b"application/json"),
            ]
        )
        assert detect_interface(scope) == INTERFACE_UI


class TestInterfaceContextVar:
    """Tests for interface_context_var behaviour."""

    def test_default_value_is_api(self) -> None:
        """ContextVar defaults to 'api' when not explicitly set."""
        assert interface_context_var.get() == INTERFACE_API

    def test_set_and_get(self) -> None:
        """Setting the ContextVar makes the value readable downstream."""
        token = interface_context_var.set(INTERFACE_UI)
        try:
            assert interface_context_var.get() == INTERFACE_UI
        finally:
            interface_context_var.reset(token)

    def test_reset_restores_default(self) -> None:
        """Resetting the ContextVar restores the default."""
        token = interface_context_var.set(INTERFACE_UI)
        interface_context_var.reset(token)
        assert interface_context_var.get() == INTERFACE_API


class TestConstants:
    """Verify public constants have expected values."""

    def test_header_name_is_lowercase(self) -> None:
        """Header constant is lowercase for ASGI comparison."""
        assert INTERFACE_HEADER == "x-orchestrator-client"

    def test_interface_values(self) -> None:
        assert INTERFACE_UI == "ui"
        assert INTERFACE_API == "api"


class TestDetectInterfaceEdgeCases:
    """Edge cases for detect_interface."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (b"ui", INTERFACE_UI),
            (b"UI", INTERFACE_UI),
            (b"api", INTERFACE_API),
            (b"cli", INTERFACE_API),
            (b"sdk", INTERFACE_API),
            (b"mcp", INTERFACE_API),
            (b"", INTERFACE_API),
        ],
    )
    def test_various_header_values(self, value: bytes, expected: str) -> None:
        """Parametrised test for different X-Orchestrator-Client values."""
        scope = _make_scope(headers=[(b"x-orchestrator-client", value)])
        assert detect_interface(scope) == expected
