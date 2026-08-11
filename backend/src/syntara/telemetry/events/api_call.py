"""API call telemetry event model.

Captures analytics for a single API request, conforming to the
ANSTRAT-1748 api_call event schema.
"""

from typing import Literal

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent


class APICallEvent(BaseTelemetryEvent):
    """Analytics event for a single API request.

    Captures endpoint path, HTTP method, status code, response time,
    and request payload size. All fields are always present (no optional keys)
    to prevent schema validation failures in Segment.

    The event is immutable (frozen) to ensure data integrity after creation.
    """

    endpoint: str = Field(
        min_length=1,
        description="Request path including resource IDs",
    )
    http_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"] = Field(
        description="HTTP request method",
    )
    status_code: int = Field(
        ge=100,
        le=599,
        description="HTTP response status code",
    )
    response_time_ms: int = Field(
        ge=0,
        description="Response time in milliseconds",
    )
    request_payload_size: int = Field(
        ge=0,
        description="Request body size in bytes from Content-Length header",
    )
