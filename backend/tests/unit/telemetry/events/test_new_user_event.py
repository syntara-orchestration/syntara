"""Unit tests for NewUserEvent model validation."""

import hashlib
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.telemetry.events.new_user import NewUserEvent

VALID_USER_ID_HASH = hashlib.sha256(str(uuid4()).encode()).hexdigest()


class TestNewUserEventConstruction:
    """Test valid construction of NewUserEvent."""

    def test_valid_oidc(self) -> None:
        event = NewUserEvent(
            user_id_hash=VALID_USER_ID_HASH,
            amr=["fed"],
            idp="okta",
            entitlement_id="",
        )
        assert event.user_id_hash == VALID_USER_ID_HASH
        assert event.amr == ["fed"]
        assert event.idp == "okta"

    def test_valid_password(self) -> None:
        event = NewUserEvent(
            user_id_hash=VALID_USER_ID_HASH,
            amr=["pwd"],
            idp="local",
            entitlement_id="",
        )
        assert event.amr == ["pwd"]
        assert event.idp == "local"


class TestNewUserEventFieldConstraints:
    """Test field validation constraints."""

    def test_short_hash_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NewUserEvent(
                user_id_hash="tooshort",
                amr=["pwd"],
                idp="local",
                entitlement_id="",
            )

    def test_long_hash_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NewUserEvent(
                user_id_hash="a" * 65,
                amr=["pwd"],
                idp="local",
                entitlement_id="",
            )


class TestNewUserEventImmutability:
    """Test that NewUserEvent is frozen/immutable."""

    def test_frozen_user_id_hash(self) -> None:
        event = NewUserEvent(
            user_id_hash=VALID_USER_ID_HASH,
            amr=["fed"],
            idp="okta",
            entitlement_id="",
        )
        with pytest.raises(ValidationError):
            event.user_id_hash = "a" * 64


class TestNewUserEventSegmentConversion:
    """Test to_segment_event output."""

    def test_event_name_is_snake_case(self) -> None:
        event = NewUserEvent(
            user_id_hash=VALID_USER_ID_HASH,
            amr=["fed"],
            idp="okta",
            entitlement_id="",
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "new_user"

    def test_to_segment_event_contains_all_fields(self) -> None:
        event = NewUserEvent(
            user_id_hash=VALID_USER_ID_HASH,
            amr=["fed"],
            idp="okta",
            entitlement_id="ent-123",
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "new_user"
        props = segment_event["properties"]
        assert props == {
            "user_id_hash": VALID_USER_ID_HASH,
            "amr": ["fed"],
            "idp": "okta",
            "entitlement_id": "ent-123",
            "request_id": None,
        }

    def test_segment_event_is_json_serializable(self) -> None:
        event = NewUserEvent(
            user_id_hash=VALID_USER_ID_HASH,
            amr=["pwd"],
            idp="local",
            entitlement_id="",
        )
        assert json.dumps(event.to_segment_event())
