"""Telling a real cancel apart from a transient Temporal activity cancellation.

Lives outside both packages so either can use it: ``invocation_executor``
imports ``OrchestrationService``, and the ``executor`` package __init__ imports
``invocation_executor``, so this cannot sit under ``executor`` without a cycle.
"""

from __future__ import annotations

from temporalio import activity as temporal_activity


def cancel_was_requested() -> bool:
    """Whether this cancellation came from a real cancel rather than worker shutdown.

    Only a requested cancel is a cancel. Every other reason Temporal cancels an
    activity -- worker shutdown on a rolling deploy, a timeout, a pause, a reset
    -- is transient, and the attempt is expected to run again. Treating those as
    terminal is wrong twice over: the retried attempt returns early on the
    ``status == CANCELLED`` guard in execute_invocation, and stream subscribers
    are told a run has ended that is about to resume.

    Outside an activity context (unit tests, direct calls) the details are
    unavailable, so fall back to treating the cancellation as requested and keep
    recording a terminal state.
    """
    try:
        details = temporal_activity.cancellation_details()
    except RuntimeError:
        return True
    if details is None:
        return True
    return bool(getattr(details, "cancel_requested", False))
