"""Unit tests for APICallEvent model validation."""

import pytest
from pydantic import ValidationError

from syntara.telemetry.events.api_call import APICallEvent


class TestAPICallEventConstruction:
    """Test valid construction of APICallEvent."""

    def test_valid_get_request(self) -> None:
        event = APICallEvent(
            endpoint="/api/v1/workflows",
            http_method="GET",
            status_code=200,
            response_time_ms=45,
            request_payload_size=0,
            entitlement_id="",
        )
        assert event.endpoint == "/api/v1/workflows"
        assert event.http_method == "GET"
        assert event.status_code == 200
        assert event.response_time_ms == 45
        assert event.request_payload_size == 0

    def test_valid_post_request(self) -> None:
        event = APICallEvent(
            endpoint="/api/v1/invocations",
            http_method="POST",
            status_code=202,
            response_time_ms=120,
            request_payload_size=1524,
            entitlement_id="",
        )
        assert event.endpoint == "/api/v1/invocations"
        assert event.http_method == "POST"
        assert event.status_code == 202
        assert event.response_time_ms == 120
        assert event.request_payload_size == 1524

    def test_valid_delete_request_server_error(self) -> None:
        event = APICallEvent(
            endpoint="/api/v1/credentials/a1b2c3d4",
            http_method="DELETE",
            status_code=500,
            response_time_ms=8,
            request_payload_size=0,
            entitlement_id="",
        )
        assert event.status_code == 500

    @pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    def test_all_valid_http_methods(self, method: str) -> None:
        event = APICallEvent(
            endpoint="/test",
            http_method=method,
            status_code=200,
            response_time_ms=1,
            request_payload_size=0,
            entitlement_id="",
        )
        assert event.http_method == method


class TestAPICallEventFieldConstraints:
    """Test field validation constraints."""

    def test_empty_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError):
            APICallEvent(
                endpoint="",
                http_method="GET",
                status_code=200,
                response_time_ms=0,
                request_payload_size=0,
                entitlement_id="",
            )

    def test_invalid_http_method_rejected(self) -> None:
        with pytest.raises(ValidationError):
            APICallEvent(
                endpoint="/test",
                http_method="INVALID",
                status_code=200,
                response_time_ms=0,
                request_payload_size=0,
                entitlement_id="",
            )

    def test_status_code_below_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            APICallEvent(
                endpoint="/test",
                http_method="GET",
                status_code=99,
                response_time_ms=0,
                request_payload_size=0,
                entitlement_id="",
            )

    def test_status_code_above_599_rejected(self) -> None:
        with pytest.raises(ValidationError):
            APICallEvent(
                endpoint="/test",
                http_method="GET",
                status_code=600,
                response_time_ms=0,
                request_payload_size=0,
                entitlement_id="",
            )

    def test_status_code_boundary_100(self) -> None:
        event = APICallEvent(
            endpoint="/test",
            http_method="GET",
            status_code=100,
            response_time_ms=0,
            request_payload_size=0,
            entitlement_id="",
        )
        assert event.status_code == 100

    def test_status_code_boundary_599(self) -> None:
        event = APICallEvent(
            endpoint="/test",
            http_method="GET",
            status_code=599,
            response_time_ms=0,
            request_payload_size=0,
            entitlement_id="",
        )
        assert event.status_code == 599

    def test_negative_response_time_rejected(self) -> None:
        with pytest.raises(ValidationError):
            APICallEvent(
                endpoint="/test",
                http_method="GET",
                status_code=200,
                response_time_ms=-1,
                request_payload_size=0,
                entitlement_id="",
            )

    def test_negative_payload_size_rejected(self) -> None:
        with pytest.raises(ValidationError):
            APICallEvent(
                endpoint="/test",
                http_method="GET",
                status_code=200,
                response_time_ms=0,
                request_payload_size=-1,
                entitlement_id="",
            )

    def test_zero_response_time_accepted(self) -> None:
        event = APICallEvent(
            endpoint="/test",
            http_method="GET",
            status_code=200,
            response_time_ms=0,
            request_payload_size=0,
            entitlement_id="",
        )
        assert event.response_time_ms == 0


class TestAPICallEventImmutability:
    """Test that APICallEvent is frozen/immutable."""

    def test_frozen_endpoint(self) -> None:
        event = APICallEvent(
            endpoint="/test",
            http_method="GET",
            status_code=200,
            response_time_ms=0,
            request_payload_size=0,
            entitlement_id="",
        )
        with pytest.raises(ValidationError):
            event.endpoint = "/changed"

    def test_frozen_status_code(self) -> None:
        event = APICallEvent(
            endpoint="/test",
            http_method="GET",
            status_code=200,
            response_time_ms=0,
            request_payload_size=0,
            entitlement_id="",
        )
        with pytest.raises(ValidationError):
            event.status_code = 500


class TestAPICallEventSegmentConversion:
    """Test to_segment_event output."""

    def test_event_name_is_snake_case(self) -> None:
        event = APICallEvent(
            endpoint="/test",
            http_method="GET",
            status_code=200,
            response_time_ms=0,
            request_payload_size=0,
            entitlement_id="",
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "api_call"

    def test_to_segment_event_contains_all_fields(self) -> None:
        event = APICallEvent(
            endpoint="/api/v1/workflows",
            http_method="GET",
            status_code=200,
            response_time_ms=45,
            request_payload_size=0,
            entitlement_id="",
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "api_call"
        props = segment_event["properties"]
        assert props == {
            "endpoint": "/api/v1/workflows",
            "http_method": "GET",
            "status_code": 200,
            "response_time_ms": 45,
            "request_payload_size": 0,
            "entitlement_id": "",
            "request_id": None,
        }

    def test_to_segment_event_properties_returns_dict(self) -> None:
        event = APICallEvent(
            endpoint="/test",
            http_method="POST",
            status_code=201,
            response_time_ms=100,
            request_payload_size=512,
            entitlement_id="",
        )
        segment_event = event.to_segment_event()
        assert isinstance(segment_event["properties"], dict)
        assert len(segment_event["properties"]) == 7

    def test_entitlement_id_in_segment_properties(self) -> None:
        """entitlement_id value must appear in segment event properties."""
        event = APICallEvent(
            endpoint="/test",
            http_method="GET",
            status_code=200,
            response_time_ms=0,
            request_payload_size=0,
            entitlement_id="ent-xyz",
        )
        segment_event = event.to_segment_event()
        props = segment_event["properties"]
        assert isinstance(props, dict)
        assert props["entitlement_id"] == "ent-xyz"
