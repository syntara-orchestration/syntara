"""API-vs-UI interface detection for request metrics tagging.

Determines whether an HTTP request originates from the Syntara UI or from an
external API consumer (CLI, CI/CD pipeline, script, MCP client).  The detected
interface is stored in a :class:`~contextvars.ContextVar` so that any
downstream middleware or instrumentation point can read it without passing the
value explicitly.

Detection strategy
------------------
The UI's ``openapi-fetch`` clients send a ``X-Orchestrator-Client: ui`` header on
every request.  Any request without this header — or with a value other than
``"ui"`` — is classified as ``"api"``.

Other teams building clients that should be classified as API consumers need
only omit the header (the default).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import Scope

INTERFACE_HEADER: str = "x-orchestrator-client"

INTERFACE_UI: str = "ui"
INTERFACE_API: str = "api"

interface_context_var: ContextVar[str] = ContextVar("interface", default=INTERFACE_API)


def detect_interface(scope: Scope) -> str:
    """Determine the originating interface from ASGI request headers.

    Scans the ``scope["headers"]`` list for the ``X-Orchestrator-Client`` header.
    Returns :data:`INTERFACE_UI` when the header value is ``"ui"``
    (case-insensitive), :data:`INTERFACE_API` otherwise.

    Args:
        scope: ASGI connection scope containing ``headers``.

    Returns:
        ``"ui"`` or ``"api"``.

    """
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    header_name = INTERFACE_HEADER.encode()
    for name, value in headers:
        if name.lower() == header_name:
            if value.decode("latin-1").strip().lower() == INTERFACE_UI:
                return INTERFACE_UI
            return INTERFACE_API
    return INTERFACE_API
