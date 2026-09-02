"""UserReference compliance tests (AAP-76837).

Discovers every registered API response model and validates that any field
typed as :class:`UserReference` is declared in its schema's
``USER_REFERENCE_FIELDS``. That declaration is what the shared
:class:`UserReferenceResolver` reads to know which fields to populate, so an
undeclared field would serialize a raw principal id — or ``null`` — while the
OpenAPI spec advertises a ``UserReference``.

How to fix a failure
--------------------
* **Undeclared field** - inherit ``UserReferenceFieldsMixin`` on the schema
  (before its other bases) and, when the field is not ``created_by`` /
  ``updated_by``, set ``USER_REFERENCE_FIELDS`` to the field names it carries.
* **Field no longer a UserReference** - drop it from ``USER_REFERENCE_FIELDS``.

This guard checks *declaration*, not runtime population: it cannot prove a
service actually calls ``resolve_user_references``. Endpoint-level integration
tests cover that.
"""

from __future__ import annotations

import typing
from typing import Any, get_args, get_origin

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from syntara.api.constants import API_V1_PATH_PREFIX
from syntara.core.models.user_reference import UserReference
from syntara.core.router_discovery import discover_and_register_routers, iter_api_routes


def _referenced_models(annotation: Any) -> set[type[BaseModel]]:  # noqa: ANN401
    """Return every pydantic model reachable from *annotation*, recursively."""
    found: set[type[BaseModel]] = set()
    stack: list[Any] = [annotation]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, type) and issubclass(current, BaseModel):
            if current in found:
                continue
            found.add(current)
            for field in current.model_fields.values():
                stack.append(field.annotation)
            continue
        stack.extend(get_args(current))
    return found


def _mentions_user_reference(annotation: Any) -> bool:  # noqa: ANN401
    """Return True if *annotation* is, or unions/contains, UserReference."""
    if annotation is UserReference:
        return True
    if get_origin(annotation) is not None or isinstance(annotation, typing.TypeVar):
        return any(_mentions_user_reference(arg) for arg in get_args(annotation))
    return False


@pytest.fixture(scope="module")
def compliance_app() -> FastAPI:
    """Build a FastAPI app with routers for route introspection only."""
    test_app = FastAPI()
    discover_and_register_routers(test_app, prefix=API_V1_PATH_PREFIX, enable_validation=False)
    return test_app


@pytest.fixture(scope="module")
def response_models(compliance_app: FastAPI) -> list[type[BaseModel]]:
    """Every pydantic model reachable from a registered route's response_model."""
    models: set[type[BaseModel]] = set()
    for route in iter_api_routes(compliance_app):
        response_model = getattr(route, "response_model", None)
        if response_model is not None:
            models |= _referenced_models(response_model)
    return sorted(models, key=lambda m: m.__name__)


def test_discovers_response_models(response_models: list[type[BaseModel]]) -> None:
    """Guard the guard: a broken walk would vacuously pass every other test here."""
    names = {m.__name__ for m in response_models}
    assert UserReference in response_models
    # Spot-check one model per shape: nested-in-list, nested-in-object, top level.
    assert {"WorkflowRead", "ExecutionRead", "ApprovalRequestRead", "GroupRead"} <= names


def test_user_reference_fields_are_declared(response_models: list[type[BaseModel]]) -> None:
    """Every UserReference-typed response field is declared for the resolver."""
    undeclared: list[str] = []
    for model in response_models:
        declared = set(getattr(model, "USER_REFERENCE_FIELDS", ()))
        for name, field in model.model_fields.items():
            if _mentions_user_reference(field.annotation) and name not in declared:
                undeclared.append(f"{model.__name__}.{name}")
    assert not undeclared, (
        "Response fields typed as UserReference but not declared in USER_REFERENCE_FIELDS "
        f"(the resolver will never populate them): {sorted(undeclared)}"
    )


def test_declared_fields_exist_and_are_user_references(response_models: list[type[BaseModel]]) -> None:
    """A stale declaration silently resolves nothing, so reject names that no longer fit."""
    stale: list[str] = []
    for model in response_models:
        for name in getattr(model, "USER_REFERENCE_FIELDS", ()):
            field = model.model_fields.get(name)
            if field is None or not _mentions_user_reference(field.annotation):
                stale.append(f"{model.__name__}.{name}")
    assert not stale, f"USER_REFERENCE_FIELDS names a field that is missing or not a UserReference: {sorted(stale)}"
