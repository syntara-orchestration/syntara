"""Loop-iteration activity id helpers for retry-from-failure.

Shared by the control plane and the engine so both
resolve ``<node>#iter-<n>`` activity names the same way. The engine needs this to
decide which activity a canvas node id refers to; the validator needs it to
normalize a selection back to base node ids.

The separator must match ``_COMPOSITE_ITER_SEP`` in activity_sync_service.py,
which is what writes the suffixed names.
"""

LOOP_ITERATION_SEP = "#iter-"


def strip_iteration_suffix(activity_name: str) -> str:
    """Normalize a loop-iteration activity name to its base node id.

    ``step_1#iter-2`` becomes ``step_1``; a name with no suffix is returned
    unchanged.
    """
    base, _, _ = activity_name.rpartition(LOOP_ITERATION_SEP)
    return base or activity_name


def has_iteration_suffix(activity_name: str) -> bool:
    """Whether an activity name carries a loop-iteration suffix."""
    return LOOP_ITERATION_SEP in activity_name
