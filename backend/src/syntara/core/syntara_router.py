"""SyntaraRouter -- drop-in replacement for FastAPI's APIRouter.

Every route registered on a ``SyntaraRouter`` carries metadata that the
authz route-scanner can inspect to derive the set of built-in policies.

Routes that intentionally skip permission checking must pass
``dependencies=[NO_PERMISSION]`` so the scanner can distinguish
"explicitly public" from "forgot to add permissions".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends


class _NoPermissionSentinel:
    """Dependency injected on routes that deliberately have no permission check."""

    async def __call__(self) -> None:
        return


NO_PERMISSION = Depends(_NoPermissionSentinel())
"""Sentinel dependency: marks a route as intentionally permission-free."""


class SyntaraRouter(APIRouter):
    """APIRouter subclass used by all Syntara domain routers.

    The route scanner limits scanning to this type. Discovery uses
    ``api_version`` and ``openapi_spec_name`` to register versioned routes
    with their matching domain contract.
    """

    api_version: str = "v1"
    openapi_spec_name: str | None = None
