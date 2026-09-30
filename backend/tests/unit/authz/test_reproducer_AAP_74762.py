"""Reproducer for AAP-74762.

POST /authz/can_i and POST /authz/who_can accept 10,000+ character strings
in the ``action``, ``resource_type``, and ``resource_id`` fields with no
length validation, unlike policy/role names which enforce a 255-char limit
(``FieldLimits.NAME_MAX_LENGTH``, see e.g. ``syntara.authz.models.policy``).

FastAPI validates a POST body against its Pydantic/SQLModel request model
before the endpoint function ever runs, so constructing ``CanIRequest`` /
``WhoCanRequest`` directly exercises the same validation the live endpoints
perform. This test expects a ``ValidationError`` for oversized fields
(the 422 the issue says should occur) — it fails on the current codebase
because no such length constraint exists.
"""

import pytest
from pydantic import ValidationError

from syntara.authz.router import CanIRequest, WhoCanRequest

_OVERSIZED = "A" * 10_000


class TestCanIRequestRejectsOversizedFields:
    """CanIRequest should enforce a max length on query fields."""

    def test_rejects_oversized_action(self) -> None:
        with pytest.raises(ValidationError):
            CanIRequest(action=_OVERSIZED, resource_type="project")

    def test_rejects_oversized_resource_type(self) -> None:
        with pytest.raises(ValidationError):
            CanIRequest(action="read", resource_type=_OVERSIZED)

    def test_rejects_oversized_resource_id(self) -> None:
        with pytest.raises(ValidationError):
            CanIRequest(action="read", resource_type="project", resource_id=_OVERSIZED)


class TestWhoCanRequestRejectsOversizedFields:
    """WhoCanRequest should enforce a max length on query fields."""

    def test_rejects_oversized_action(self) -> None:
        with pytest.raises(ValidationError):
            WhoCanRequest(action=_OVERSIZED, resource_type="project")

    def test_rejects_oversized_resource_type(self) -> None:
        with pytest.raises(ValidationError):
            WhoCanRequest(action="read", resource_type=_OVERSIZED)
