"""Custom uvicorn HTTP protocol subclasses for TLS client cert injection.

Uvicorn does not natively expose client certificates in the ASGI scope.
These subclasses override the protocol layer to extract the peer certificate
from the asyncio transport (set during the TLS handshake) and inject it into
``scope["extensions"]["tls"]["peercert"]`` before the ASGI application runs.

Downstream middleware (``ClientCertAuthMiddleware``) reads this scope
extension to authenticate service-to-service requests.

``TLSAutoProtocol`` selects the correct subclass based on whether
``httptools`` is installed (matching uvicorn's own auto-detection).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from uvicorn.protocols.http.h11_impl import H11Protocol

if TYPE_CHECKING:
    import asyncio


def _extract_peercert(transport: asyncio.Transport) -> dict[str, Any] | None:
    ssl_object = transport.get_extra_info("ssl_object")
    if ssl_object is not None:
        peercert: dict[str, Any] | None = ssl_object.getpeercert()
        return peercert
    return None


def _inject_peercert_into_scope(scope: dict[str, Any], peercert: dict[str, Any]) -> None:
    scope.setdefault("extensions", {})["tls"] = {"peercert": peercert}


class TLSH11Protocol(H11Protocol):
    """H11-based HTTP protocol that injects client certs into ASGI scope."""

    _peercert: dict[str, Any] | None

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]  # noqa: D102
        super().connection_made(transport)
        self._peercert = _extract_peercert(transport)

    def handle_events(self) -> None:  # noqa: D102
        super().handle_events()
        if self._peercert and self.scope is not None and "tls" not in self.scope.get("extensions", {}):
            _inject_peercert_into_scope(self.scope, self._peercert)  # type: ignore[arg-type]


try:
    from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol

    class TLSHttpToolsProtocol(HttpToolsProtocol):
        """Httptools-based HTTP protocol that injects client certs into ASGI scope."""

        _peercert: dict[str, Any] | None

        def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]  # noqa: D102
            super().connection_made(transport)
            self._peercert = _extract_peercert(transport)

        def on_headers_complete(self) -> None:  # noqa: D102
            super().on_headers_complete()
            if self._peercert and self.scope is not None:
                _inject_peercert_into_scope(self.scope, self._peercert)  # type: ignore[arg-type]

    TLSAutoProtocol: type[asyncio.Protocol] = TLSHttpToolsProtocol

except ImportError:
    TLSAutoProtocol = TLSH11Protocol
