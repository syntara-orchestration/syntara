"""Problem Details model for LLM provider and streaming errors."""

from typing import ClassVar

from pydantic import ConfigDict

from syntara.core.models.error import ErrorData

_EXAMPLE_INVOCATION_PATH = "/invocations/550e8400-e29b-41d4-a716-446655440000"


class LLMErrorData(ErrorData):
    """RFC 9457 error data for LLM provider and streaming failures."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "type": "https://api.example.com/errors/llm-error",
                    "title": "LLM Rate Limit Exceeded",
                    "detail": "OpenRouter API rate limit exceeded. Please try again in a few moments.",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "retryable": True,
                    "instance": _EXAMPLE_INVOCATION_PATH,
                },
                {
                    "type": "https://api.example.com/errors/timeout-error",
                    "title": "Streaming Timeout",
                    "detail": "LLM streaming timed out after 30 seconds",
                    "code": "STREAM_TIMEOUT",
                    "retryable": True,
                    "instance": _EXAMPLE_INVOCATION_PATH,
                },
            ]
        },
    )
