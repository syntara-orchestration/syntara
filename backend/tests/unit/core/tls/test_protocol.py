"""Tests for custom uvicorn TLS protocol subclasses."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Generator

import pytest

from syntara.core.tls.protocol import TLSH11Protocol, _extract_peercert, _inject_peercert_into_scope


def _make_peercert(cn: str = "worker.ao.svc") -> dict[str, Any]:
    return {"subject": ((("commonName", cn),),)}


def _make_ssl_transport(peercert: dict[str, Any] | None = None) -> MagicMock:
    transport = MagicMock(spec=["get_extra_info"])
    ssl_object = MagicMock()
    ssl_object.getpeercert.return_value = peercert

    def get_extra_info(key: str, default: object = None) -> object:
        if key == "ssl_object":
            return ssl_object if peercert is not None else None
        if key == "sslcontext":
            return MagicMock() if peercert is not None else None
        if key == "peername":
            return ("127.0.0.1", 12345)
        if key == "sockname":
            return ("127.0.0.1", 8000)
        if key == "socket":
            return MagicMock()
        return default

    transport.get_extra_info = get_extra_info
    return transport


@pytest.fixture
def proto_event_loop() -> Generator[asyncio.AbstractEventLoop]:
    # Not prefixed with _ because the value is injected into tests as _loop= kwarg.
    """Provide an event loop for protocol __init__ (requires one even in sync tests)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestExtractPeercert:
    """Tests for the _extract_peercert helper."""

    def test_extracts_from_ssl_transport(self) -> None:
        cert = _make_peercert()
        transport = _make_ssl_transport(cert)
        assert _extract_peercert(transport) == cert

    def test_returns_none_for_non_ssl(self) -> None:
        transport = _make_ssl_transport(None)
        assert _extract_peercert(transport) is None


class TestInjectPeercertIntoScope:
    """Tests for the _inject_peercert_into_scope helper."""

    def test_injects_into_empty_scope(self) -> None:
        scope: dict[str, Any] = {"type": "http"}
        cert = _make_peercert()
        _inject_peercert_into_scope(scope, cert)
        assert scope["extensions"]["tls"]["peercert"] == cert

    def test_preserves_existing_extensions(self) -> None:
        scope: dict[str, Any] = {"type": "http", "extensions": {"other": "data"}}
        cert = _make_peercert()
        _inject_peercert_into_scope(scope, cert)
        assert scope["extensions"]["tls"]["peercert"] == cert
        assert scope["extensions"]["other"] == "data"


class TestTLSH11Protocol:
    """Tests for the H11-based TLS protocol subclass."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Minimal uvicorn Config mock for H11Protocol."""
        config = MagicMock()
        config.loaded = True
        config.loaded_app = MagicMock()
        config.asgi_version = "3.0"
        config.root_path = ""
        config.limit_concurrency = None
        config.timeout_keep_alive = 5
        config.ws_protocol_class = None
        config.h11_max_incomplete_event_size = None
        return config

    @pytest.fixture
    def mock_server_state(self) -> MagicMock:
        """Minimal uvicorn ServerState mock."""
        state = MagicMock()
        state.connections = set()
        state.tasks = set()
        state.default_headers = []
        return state

    @pytest.mark.usefixtures("proto_event_loop")
    def test_connection_made_caches_peercert(
        self, mock_config: MagicMock, mock_server_state: MagicMock, proto_event_loop: asyncio.AbstractEventLoop
    ) -> None:
        protocol = TLSH11Protocol(mock_config, mock_server_state, {}, _loop=proto_event_loop)
        cert = _make_peercert("backend.ao.svc")
        transport = _make_ssl_transport(cert)

        protocol.connection_made(transport)

        assert protocol._peercert == cert

    @pytest.mark.usefixtures("proto_event_loop")
    def test_connection_made_no_ssl(
        self, mock_config: MagicMock, mock_server_state: MagicMock, proto_event_loop: asyncio.AbstractEventLoop
    ) -> None:
        protocol = TLSH11Protocol(mock_config, mock_server_state, {}, _loop=proto_event_loop)
        transport = _make_ssl_transport(None)

        protocol.connection_made(transport)

        assert protocol._peercert is None

    @pytest.mark.usefixtures("proto_event_loop")
    def test_handle_events_injects_peercert(
        self, mock_config: MagicMock, mock_server_state: MagicMock, proto_event_loop: asyncio.AbstractEventLoop
    ) -> None:
        protocol = TLSH11Protocol(mock_config, mock_server_state, {}, _loop=proto_event_loop)
        cert = _make_peercert()
        protocol._peercert = cert
        protocol.scope = {"type": "http", "state": {}}  # type: ignore[typeddict-item]

        with patch.object(TLSH11Protocol.__bases__[0], "handle_events"):
            protocol.handle_events()

        assert protocol.scope["extensions"]["tls"]["peercert"] == cert

    @pytest.mark.usefixtures("proto_event_loop")
    def test_handle_events_skips_when_no_cert(
        self, mock_config: MagicMock, mock_server_state: MagicMock, proto_event_loop: asyncio.AbstractEventLoop
    ) -> None:
        protocol = TLSH11Protocol(mock_config, mock_server_state, {}, _loop=proto_event_loop)
        protocol._peercert = None
        protocol.scope = {"type": "http", "state": {}}  # type: ignore[typeddict-item]

        with patch.object(TLSH11Protocol.__bases__[0], "handle_events"):
            protocol.handle_events()

        assert "extensions" not in protocol.scope


try:
    from syntara.core.tls.protocol import TLSHttpToolsProtocol

    class TestTLSHttpToolsProtocol:
        """Tests for the httptools-based TLS protocol subclass."""

        @pytest.fixture
        def mock_config(self) -> MagicMock:
            """Minimal uvicorn Config mock for HttpToolsProtocol."""
            config = MagicMock()
            config.loaded = True
            config.loaded_app = MagicMock()
            config.asgi_version = "3.0"
            config.root_path = ""
            config.limit_concurrency = None
            config.timeout_keep_alive = 5
            config.ws_protocol_class = None
            return config

        @pytest.fixture
        def mock_server_state(self) -> MagicMock:
            """Minimal uvicorn ServerState mock."""
            state = MagicMock()
            state.connections = set()
            state.tasks = set()
            state.default_headers = []
            return state

        @pytest.mark.usefixtures("proto_event_loop")
        def test_connection_made_caches_peercert(
            self, mock_config: MagicMock, mock_server_state: MagicMock, proto_event_loop: asyncio.AbstractEventLoop
        ) -> None:
            protocol = TLSHttpToolsProtocol(mock_config, mock_server_state, {}, _loop=proto_event_loop)
            cert = _make_peercert("backend.ao.svc")
            transport = _make_ssl_transport(cert)

            protocol.connection_made(transport)

            assert protocol._peercert == cert

        @pytest.mark.usefixtures("proto_event_loop")
        def test_connection_made_no_ssl(
            self, mock_config: MagicMock, mock_server_state: MagicMock, proto_event_loop: asyncio.AbstractEventLoop
        ) -> None:
            protocol = TLSHttpToolsProtocol(mock_config, mock_server_state, {}, _loop=proto_event_loop)
            transport = _make_ssl_transport(None)

            protocol.connection_made(transport)

            assert protocol._peercert is None

        @pytest.mark.usefixtures("proto_event_loop")
        def test_on_headers_complete_injects_peercert(
            self, mock_config: MagicMock, mock_server_state: MagicMock, proto_event_loop: asyncio.AbstractEventLoop
        ) -> None:
            protocol = TLSHttpToolsProtocol(mock_config, mock_server_state, {}, _loop=proto_event_loop)
            cert = _make_peercert()
            protocol._peercert = cert
            protocol.scope = None  # type: ignore[assignment]

            with patch.object(TLSHttpToolsProtocol.__bases__[0], "on_headers_complete"):
                protocol.scope = {"type": "http", "state": {}}  # type: ignore[typeddict-item]
                protocol.on_headers_complete()

            assert protocol.scope["extensions"]["tls"]["peercert"] == cert

        @pytest.mark.usefixtures("proto_event_loop")
        def test_on_headers_complete_skips_when_no_cert(
            self, mock_config: MagicMock, mock_server_state: MagicMock, proto_event_loop: asyncio.AbstractEventLoop
        ) -> None:
            protocol = TLSHttpToolsProtocol(mock_config, mock_server_state, {}, _loop=proto_event_loop)
            protocol._peercert = None
            protocol.scope = None  # type: ignore[assignment]

            with patch.object(TLSHttpToolsProtocol.__bases__[0], "on_headers_complete"):
                protocol.scope = {"type": "http", "state": {}}  # type: ignore[typeddict-item]
                protocol.on_headers_complete()

            assert "extensions" not in protocol.scope

except ImportError:
    pass
