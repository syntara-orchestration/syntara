"""Parse schedule trigger configurations into Temporal Schedule objects.

Converts UI-provided schedule configurations (ISO 8601 intervals, cron
expressions) into Temporal SDK ``ScheduleSpec`` and ``SchedulePolicy``
objects used to create and manage Temporal Schedules.
"""

import re
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
from syntara.workflows.workflow_engine.models.workflow_definition import MissedSchedulePolicy, ScheduleType

# ISO 8601 repeating interval pattern: R[n]/<start>/<duration>[/<end>]
# Examples: R/2024-01-01T10:00:00Z/P1D, R/2024-01-01T00:00:00Z/P7D/2024-12-31T23:59:59Z
_REPEATING_INTERVAL_PATTERN = re.compile(
    r"^R(\d+)?/"  # R[repetitions]/
    r"([^/]+)/"  # ISO datetime start
    r"(P[^/]+)"  # ISO 8601 duration
    r"(?:/([^/]+))?$"  # optional /end
)

# ISO 8601 duration pattern: P[nY][nM][nW][nD][T[nH][nM][nS]]
_DURATION_PATTERN = re.compile(
    r"^P"
    r"(?:(\d+)Y)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+)W)?"
    r"(?:(\d+)D)?"
    r"(?:T"
    r"(?:(\d+)H)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+(?:\.\d+)?)S)?"
    r")?$"
)

# Catchup window for missed schedule policies
_CATCHUP_WINDOW_SKIP = timedelta(seconds=1)
_CATCHUP_WINDOW_RECOVER = timedelta(hours=48)


def parse_iso8601_duration(duration_str: str) -> timedelta:
    """Parse an ISO 8601 duration string into a timedelta.

    Supports fixed-length durations: P1D, P7D, P1W, PT1H, PT30M, PT1H30M,
    and compound forms like P1DT12H30M.

    Durations containing months or years (e.g. P1M, P1Y) are rejected because
    they cannot be represented as a fixed timedelta.  Use calendar-based specs
    or cron expressions for those intervals.

    Args:
        duration_str: ISO 8601 duration (e.g., "P1D", "PT1H30M").

    Returns:
        Equivalent timedelta.

    Raises:
        SafeValueError: If the duration string is invalid, empty, or contains
            months/years.

    """
    match = _DURATION_PATTERN.match(duration_str)
    if not match:
        msg = f"Invalid ISO 8601 duration: '{duration_str}'"
        raise SafeValueError(msg)

    years = int(match.group(1) or 0)
    months = int(match.group(2) or 0)
    if years or months:
        msg = (
            f"Duration with months or years cannot be converted to a fixed timedelta: "
            f"'{duration_str}'. Use a cron expression for calendar-based schedules."
        )
        raise SafeValueError(msg)

    weeks = int(match.group(3) or 0)
    days = int(match.group(4) or 0)
    hours = int(match.group(5) or 0)
    minutes = int(match.group(6) or 0)
    seconds = float(match.group(7) or 0)

    total = timedelta(
        days=weeks * 7 + days,
        hours=hours,
        minutes=minutes,
        seconds=seconds,
    )

    if total == timedelta():
        msg = f"ISO 8601 duration must be non-zero: '{duration_str}'"
        raise SafeValueError(msg)

    return total


def _parse_iso_datetime(dt_str: str) -> datetime:
    """Parse an ISO 8601 datetime string to a timezone-aware datetime.

    Raises:
        SafeValueError: If the string is not valid ISO 8601 or lacks timezone info.

    """
    try:
        dt = datetime.fromisoformat(dt_str)
    except ValueError as e:
        msg = f"Invalid ISO 8601 datetime: '{dt_str}'"
        raise SafeValueError(msg) from e
    if dt.tzinfo is None:
        msg = f"Datetime must include timezone info: '{dt_str}'"
        raise SafeValueError(msg)
    return dt


def _has_calendar_components(duration_str: str) -> tuple[int, int, bool]:
    """Return (years, months, has_fixed) parsed from an ISO 8601 duration string.

    ``has_fixed`` is True when the duration also contains weeks, days, hours,
    minutes, or seconds alongside calendar components.

    Returns (0, 0, False) when the duration contains no calendar components.
    """
    match = _DURATION_PATTERN.match(duration_str)
    if not match:
        return (0, 0, False)
    years = int(match.group(1) or 0)
    months = int(match.group(2) or 0)
    # Groups 3-7: weeks, days, hours, minutes, seconds
    has_fixed = bool(
        int(match.group(3) or 0)
        or int(match.group(4) or 0)
        or int(match.group(5) or 0)
        or int(match.group(6) or 0)
        or float(match.group(7) or 0)
    )
    return (years, months, has_fixed)


_REPRESENTABLE_MONTH_STEPS = frozenset({1, 2, 3, 4, 6})


def _interval_to_calendar_spec(start: datetime, total_months: int) -> ScheduleCalendarSpec:
    """Build a calendar spec that repeats every *total_months* months.

    Uses the start datetime to derive the minute, hour, and day-of-month.
    The month range offset is calculated so the schedule always fires in the
    start month and wraps correctly across year boundaries.

    Raises:
        SafeValueError: If *total_months* cannot be represented as a calendar
            spec (e.g. 5, 7, or multi-year intervals).

    """
    if total_months < 12 and start.day > 28:  # noqa: PLR2004
        msg = (
            f"Day-of-month {start.day} is not valid for monthly schedules because "
            "not all months have that many days. Use a start date with day <= 28, "
            "or use a cron expression for more control."
        )
        raise SafeValueError(msg)

    if total_months == 12:  # noqa: PLR2004
        month_ranges: list[ScheduleRange] = [ScheduleRange(start.month)]
    elif total_months in _REPRESENTABLE_MONTH_STEPS:
        offset = ((start.month - 1) % total_months) + 1
        month_ranges = [ScheduleRange(offset, 12, step=total_months)]
    else:
        msg = (
            f"Calendar interval of {total_months} months cannot be represented "
            "as a schedule. Use 1, 2, 3, 4, 6, or 12 months, or a cron expression."
        )
        raise SafeValueError(msg)

    return ScheduleCalendarSpec(
        minute=[ScheduleRange(start.minute)],
        hour=[ScheduleRange(start.hour)],
        day_of_month=[ScheduleRange(start.day)],
        month=month_ranges,
    )


def parse_iso8601_interval(interval: str, tz: str | None = None) -> ScheduleSpec:
    """Parse an ISO 8601 repeating interval into a Temporal ScheduleSpec.

    Supports formats:
    - ``R/<start>/<duration>`` — repeat indefinitely from start
    - ``R/<start>/<duration>/<end>`` — repeat from start until end

    Finite repetition counts (e.g. ``R1``, ``R5``) are not supported.
    Use an end date to limit the number of executions.

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
    match = _REPEATING_INTERVAL_PATTERN.match(interval)
    if not match:
        msg = f"Invalid ISO 8601 repeating interval: '{interval}'"
        raise SafeValueError(msg)

    repetitions_str = match.group(1)
    start_str = match.group(2)
    duration_str = match.group(3)
    end_str = match.group(4)

    if repetitions_str:
        msg = (
            f"Finite repetition count R{repetitions_str} is not supported. "
            "Set an end date to limit the number of executions."
        )
        raise SafeValueError(msg)

    start_at = _parse_iso_datetime(start_str)
    end_at = _parse_iso_datetime(end_str) if end_str else None

    years, months, has_fixed = _has_calendar_components(duration_str)
    if years or months:
        if has_fixed:
            msg = (
                f"Mixed calendar and fixed durations are not supported: "
                f"'{duration_str}'. Separate months/years from days/hours/minutes, "
                "or use a cron expression."
            )
            raise SafeValueError(msg)
        total_months = years * 12 + months
        cal_spec = _interval_to_calendar_spec(start_at, total_months)
        return ScheduleSpec(
            calendars=[cal_spec],
            start_at=start_at,
            end_at=end_at,
            time_zone_name=tz or "UTC",
        )

    duration = parse_iso8601_duration(duration_str)

    return ScheduleSpec(
        intervals=[ScheduleIntervalSpec(every=duration)],
        start_at=start_at,
        end_at=end_at,
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


SCHEDULE_ID_PREFIX = "nexus-sched-"


def build_schedule_id(workflow_id: str, trigger_node_id: str) -> str:
    """Build a deterministic Temporal Schedule ID.

    Convention: ``nexus-sched-{workflow_id}-{trigger_node_id}``

    Args:
        workflow_id: The workflow UUID (as string).
        trigger_node_id: The trigger node ID within the workflow definition.

    Returns:
        Deterministic schedule ID string.

    """
    return f"{SCHEDULE_ID_PREFIX}{workflow_id}-{trigger_node_id}"


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
    "build_schedule_id",
    "build_schedule_policy",
    "config_to_temporal_schedule",
    "parse_cron_to_spec",
    "parse_iso8601_duration",
    "parse_iso8601_interval",
]
