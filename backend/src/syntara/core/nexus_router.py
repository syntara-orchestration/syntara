"""NexusRouter -- drop-in replacement for FastAPI's APIRouter.

Every route registered on a ``NexusRouter`` carries metadata that the
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


class NexusRouter(APIRouter):
    """APIRouter subclass used by all Nexus domain routers.

    Currently identical to ``APIRouter`` in behaviour; the type is used
    by the route scanner to limit scanning to Nexus-owned routes.
    """
