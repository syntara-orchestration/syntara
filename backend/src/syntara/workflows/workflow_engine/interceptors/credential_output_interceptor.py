"""Activity interceptor for marking credential-bearing output for encryption.

When an activity receives resolved credentials in its input, its output
may contain credential values (e.g., in stdout, HTTP response bodies).
This interceptor adds a ``_has_credentials`` marker to such outputs so
the PayloadCodec encrypts them in Temporal history.
"""

from collections.abc import Sequence
from typing import Any

from temporalio.exceptions import ApplicationError
from temporalio.worker import (
    ActivityInboundInterceptor,
    ExecuteActivityInput,
    Interceptor,
)


def _input_has_credentials(args: Sequence[Any]) -> bool:
    """Check if activity args contain resolved credentials."""
    return bool(args) and isinstance(args[0], dict) and "_resolved_credentials" in args[0]


def _mark_error_details(exc: ApplicationError) -> None:
    """Add _has_credentials marker to ApplicationError details for codec encryption.

    Only dict-typed details can carry the marker. All current activities use dict
    details for output data (which is where credential values appear). String-typed
    details are error messages that don't contain credential values.
    """
    for detail in exc.details:
        if isinstance(detail, dict):
            detail["_has_credentials"] = True


class _CredentialOutputActivityInterceptor(ActivityInboundInterceptor):
    """Marks activity results for encryption when the input contained credentials."""

    async def execute_activity(self, input: ExecuteActivityInput) -> Any:  # noqa: A002, ANN401
        has_creds = _input_has_credentials(input.args)
        if not has_creds:
            return await super().execute_activity(input)

        try:
            result = await super().execute_activity(input)
        except ApplicationError as exc:
            _mark_error_details(exc)
            raise
        else:
            if isinstance(result, dict):
                result["_has_credentials"] = True
            return result


class CredentialOutputInterceptor(Interceptor):
    """Interceptor that marks credential-bearing activity output for encryption."""

    def intercept_activity(self, next_interceptor: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        """Return the activity interceptor that adds credential markers."""
        return _CredentialOutputActivityInterceptor(next_interceptor)
