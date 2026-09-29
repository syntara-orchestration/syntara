"""Reproducer for AAP-91652.

The AAP-74760 fix added a 405 entry to ``http_exception_handler``'s status
mapping, but the handler is only registered against ``fastapi.HTTPException``
(see ``app.add_exception_handler(HTTPException, core_http_exception_handler)``
in ``syntara/api/main.py``). A 405/404 for a valid path with an unsupported
method is raised by Starlette's router as ``starlette.exceptions.HTTPException``
directly — before FastAPI ever wraps it in ``fastapi.exceptions.HTTPException`` —
so it bypasses that handler and falls back to Starlette's plain
``{"detail": ...}`` response instead of the RFC 9457 problem+json format.

This registers a throwaway route directly on the real, already-imported
production ``app`` object (the module-level ``app.add_exception_handler(...)``
call in ``main.py`` has already run at import time) so the test exercises the
actual production exception-handler wiring without needing the full
lifespan startup (DB/Redis/Temporal are not available in this sandbox).
"""

from __future__ import annotations

from starlette.testclient import TestClient

_TEST_ROUTE_PATH = "/__test_reproducer_aap_91652__"


class TestRouterLevel405IsRFC9457:
    """A 405 from the Starlette router should still be RFC 9457 formatted."""

    def test_method_not_allowed_returns_rfc7807(self) -> None:
        from syntara.api.main import app as real_app

        @real_app.get(_TEST_ROUTE_PATH, include_in_schema=False)
        async def _reproducer_route() -> dict[str, bool]:
            return {"ok": True}

        try:
            client = TestClient(real_app, raise_server_exceptions=False)

            response = client.delete(_TEST_ROUTE_PATH)

            assert response.status_code == 405
            body = response.json()
            # This app's ErrorData/RFC 9457 shape (see syntara.core.models.error.ErrorData
            # and the app-level handler's status_mapping for 405) always includes these
            # fields. Starlette's default 405 response body is just {"detail": "..."}.
            assert "type" in body, f"Expected RFC 9457 'type' field, got: {body}"
            assert "title" in body, f"Expected RFC 9457 'title' field, got: {body}"
            assert "code" in body, f"Expected RFC 9457 'code' field, got: {body}"
        finally:
            real_app.router.routes = [r for r in real_app.router.routes if getattr(r, "path", None) != _TEST_ROUTE_PATH]
