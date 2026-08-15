"""Parse schedule trigger configurations into Temporal Schedule objects.

Converts UI-provided schedule configurations (ISO 8601 intervals, cron
expressions) into Temporal SDK ``ScheduleSpec`` and ``SchedulePolicy``
objects used to create and manage Temporal Schedules.
"""

from datetime import datetime, timedelta
from typing import Any

from temporalio.client import (
    ScheduleCalendarSpec,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleRange,
    ScheduleSpec,
)

from syntara.core.exceptions import SafeValueError
from syntara.workflows.utils.iso8601_interval import (
    parse_iso8601_duration as parse_iso8601_duration,  # noqa: PLC0414 - re-exported for callers/tests
)
from syntara.workflows.utils.iso8601_interval import (
    parse_iso8601_repeating_interval,
    validate_calendar_step,
)
from syntara.workflows.workflow_engine.models.workflow_definition import MissedSchedulePolicy, ScheduleType

# Catchup window for missed schedule policies
_CATCHUP_WINDOW_SKIP = timedelta(seconds=1)
_CATCHUP_WINDOW_RECOVER = timedelta(hours=48)


def _interval_to_calendar_spec(start: datetime, total_months: int) -> ScheduleCalendarSpec:
    """Build a calendar spec that repeats every *total_months* months.

    Uses the start datetime to derive the minute, hour, and day-of-month.
    The month range offset is calculated so the schedule always fires in the
    start month and wraps correctly across year boundaries.

    Raises:
        SafeValueError: If *total_months* cannot be represented as a calendar
            spec (e.g. 5, 7, or multi-year intervals). See
            ``iso8601_interval.validate_calendar_step`` for the shared check.

    """
    validate_calendar_step(start.day, total_months)

    if total_months == 12:  # noqa: PLR2004
        month_ranges: list[ScheduleRange] = [ScheduleRange(start.month)]
    else:
        offset = ((start.month - 1) % total_months) + 1
        month_ranges = [ScheduleRange(offset, 12, step=total_months)]

    return ScheduleCalendarSpec(
        minute=[ScheduleRange(start.minute)],
        hour=[ScheduleRange(start.hour)],
        day_of_month=[ScheduleRange(start.day)],
        month=month_ranges,
    )


def parse_iso8601_interval(interval: str, tz: str | None = None) -> ScheduleSpec:
    """Parse an ISO 8601 repeating interval into a Temporal ScheduleSpec.

    Delegates all parsing and semantic validation to
    ``iso8601_interval.parse_iso8601_repeating_interval`` (the single source
    of truth shared with ``ScheduledTriggerConfig.validate_interval_expression``)
    and only builds Temporal SDK objects here.

    Durations containing months or years (e.g. P1M, P1Y) are automatically
    converted to calendar specs so Temporal can evaluate them with full
    calendar awareness instead of approximating with fixed-day timedeltas.

    Args:
        interval: ISO 8601 repeating interval string.
        tz: Optional IANA timezone name.

    Returns:
        Temporal ScheduleSpec with intervals and optional start/end times.

    Raises:
        SafeValueError: If the interval string is invalid.

    """
    parsed = parse_iso8601_repeating_interval(interval)

    if parsed.calendar_months is not None:
        cal_spec = _interval_to_calendar_spec(parsed.start_at, parsed.calendar_months)
        return ScheduleSpec(
            calendars=[cal_spec],
            start_at=parsed.start_at,
            end_at=parsed.end_at,
            time_zone_name=tz or "UTC",
        )

    if parsed.duration is None:
        msg = f"Invalid ISO 8601 repeating interval: '{interval}'"
        raise SafeValueError(msg)

    return ScheduleSpec(
        intervals=[ScheduleIntervalSpec(every=parsed.duration)],
        start_at=parsed.start_at,
        end_at=parsed.end_at,
        time_zone_name=tz or "UTC",
    )


def parse_cron_to_spec(cron: str, tz: str | None = None) -> ScheduleSpec:
    """Convert a 5-field cron expression into a Temporal ScheduleSpec.

    Args:
        cron: Standard 5-field cron expression (minute hour day-of-month month day-of-week).
        tz: Optional IANA timezone name. Defaults to UTC.

    Returns:
        Temporal ScheduleSpec with the cron expression.

    """
    return ScheduleSpec(
        cron_expressions=[cron],
        time_zone_name=tz or "UTC",
    )


def build_schedule_policy(missed_policy: MissedSchedulePolicy) -> SchedulePolicy:
    """Map a MissedSchedulePolicy to a Temporal SchedulePolicy.

    Args:
        missed_policy: How to handle overlapping schedule executions.

    Returns:
        Temporal SchedulePolicy with appropriate catchup_window and overlap policy.

    """
    overlap_map = {
        MissedSchedulePolicy.SKIP: ScheduleOverlapPolicy.SKIP,
        MissedSchedulePolicy.BUFFER_ONE: ScheduleOverlapPolicy.BUFFER_ONE,
        MissedSchedulePolicy.BUFFER_ALL: ScheduleOverlapPolicy.BUFFER_ALL,
        MissedSchedulePolicy.ALLOW_ALL: ScheduleOverlapPolicy.ALLOW_ALL,
        MissedSchedulePolicy.CANCEL_OTHER: ScheduleOverlapPolicy.CANCEL_OTHER,
    }
    overlap = overlap_map[missed_policy]
    # SKIP and CANCEL_OTHER discard missed fires — no catchup.
    # BUFFER_ONE, BUFFER_ALL, ALLOW_ALL recover missed fires within 48h.
    no_catchup = missed_policy in (MissedSchedulePolicy.SKIP, MissedSchedulePolicy.CANCEL_OTHER)
    catchup = _CATCHUP_WINDOW_SKIP if no_catchup else _CATCHUP_WINDOW_RECOVER
    return SchedulePolicy(catchup_window=catchup, overlap=overlap)


SCHEDULE_ID_PREFIX = "orchestrator-sched-"


def build_schedule_id(workflow_id: str, trigger_node_id: str) -> str:
    """Build a deterministic Temporal Schedule ID.

    Convention: ``orchestrator-sched-{workflow_id}-{trigger_node_id}``

    Args:
        workflow_id: The workflow UUID (as string).
        trigger_node_id: The trigger node ID within the workflow definition.

    Returns:
        Deterministic schedule ID string.

    """
    return f"{SCHEDULE_ID_PREFIX}{workflow_id}-{trigger_node_id}"


def build_schedule_execution_workflow_id(workflow_id: str, trigger_node_id: str) -> str:
    """Build the Temporal workflow ID used when a schedule fires its launcher.

    Convention: ``sched-exec-{workflow_id}-{trigger_node_id}``

    Temporal appends an RFC3339 UTC timestamp suffix on each fire; verification
    normalizes that suffix in ``workflow_auth._auth_workflow_id``.
    """
    return f"sched-exec-{workflow_id}-{trigger_node_id}"


def config_to_temporal_schedule(
    config: dict[str, Any],
) -> tuple[ScheduleSpec, SchedulePolicy]:
    """Convert a scheduled trigger config dict to Temporal Schedule objects.

    Args:
        config: Trigger config dict with schedule_type, interval/cron, timezone,
            and missed_schedule_policy fields.

    Returns:
        Tuple of (ScheduleSpec, SchedulePolicy).

    Raises:
        SafeValueError: If the config is invalid or missing required fields.

    """
    schedule_type = config.get("schedule_type")
    tz = config.get("timezone")
    missed_policy_raw = config.get("missed_schedule_policy")
    if missed_policy_raw:
        try:
            missed_policy = MissedSchedulePolicy(missed_policy_raw)
        except ValueError:
            msg = f"Unknown missed_schedule_policy: '{missed_policy_raw}'"
            raise SafeValueError(msg) from None
    else:
        missed_policy = MissedSchedulePolicy.SKIP

    if schedule_type == ScheduleType.INTERVAL:
        interval = config.get("interval")
        if not interval:
            msg = "interval is required for schedule_type 'interval'"
            raise SafeValueError(msg)
        spec = parse_iso8601_interval(interval, tz)
    elif schedule_type == ScheduleType.CRON:
        cron = config.get("cron")
        if not cron:
            msg = "cron is required for schedule_type 'cron'"
            raise SafeValueError(msg)
        spec = parse_cron_to_spec(cron, tz)
    else:
        msg = f"Unknown schedule_type: '{schedule_type}'"
        raise SafeValueError(msg)

    policy = build_schedule_policy(missed_policy)

    return spec, policy


# Re-export for convenience
__all__ = [
    "build_schedule_execution_workflow_id",
    "build_schedule_id",
    "build_schedule_policy",
    "config_to_temporal_schedule",
    "parse_cron_to_spec",
    "parse_iso8601_duration",
    "parse_iso8601_interval",
]
