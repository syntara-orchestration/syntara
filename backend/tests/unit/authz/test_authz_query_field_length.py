"""Unit tests for authz query field length validation (AAP-74762).

can_i and who_can accept 10,000+ character strings in action, resource_type,
and resource_id with no length validation, unlike policy/role names which
enforce a 255-char limit via NameField. Oversized query fields should be
rejected with a pydantic ValidationError instead of being accepted silently.
"""

import pytest
from pydantic import ValidationError

from syntara.authz.router import CanIRequest, WhoCanRequest


class TestCanIRequestFieldLength:
    """CanIRequest should reject unreasonably long query fields."""

    def test_rejects_long_action(self) -> None:
        with pytest.raises(ValidationError):
            CanIRequest(action="a" * 10000, resource_type="workflow")

    def test_rejects_long_resource_type(self) -> None:
        with pytest.raises(ValidationError):
            CanIRequest(action="read", resource_type="x" * 10000)

    def test_rejects_long_resource_id(self) -> None:
        with pytest.raises(ValidationError):
            CanIRequest(action="read", resource_type="workflow", resource_id="r" * 10000)


class TestWhoCanRequestFieldLength:
    """WhoCanRequest should reject unreasonably long query fields."""

    def test_rejects_long_action(self) -> None:
        with pytest.raises(ValidationError):
            WhoCanRequest(action="a" * 10000, resource_type="workflow")

    def test_rejects_long_resource_type(self) -> None:
        with pytest.raises(ValidationError):
            WhoCanRequest(action="read", resource_type="x" * 10000)

    def test_rejects_long_resource_id(self) -> None:
        with pytest.raises(ValidationError):
            WhoCanRequest(action="read", resource_type="workflow", resource_id="r" * 10000)
