"""Parse and validate ISO 8601 repeating interval strings.

Single source of truth for interval semantics — format, finite-repetition
rejection, timezone-aware datetimes, duration validity, calendar/fixed
mixing, and month-step representability. Deliberately has no dependency on
``temporalio`` or on ``workflow_engine.models.workflow_definition``, so it can
be imported from both:

- ``ScheduledTriggerConfig.validate_interval_expression`` (Pydantic model,
  used by ``/workflows/validate``, publish, and Temporal sync) — without
  pulling the Temporal SDK into the model/validation path.
- ``syntara.workflows.utils.schedule_parser`` (Temporal schedule
  construction) — without duplicating the parsing logic.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from syntara.core.exceptions import SafeValueError

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

_REPRESENTABLE_MONTH_STEPS = frozenset({1, 2, 3, 4, 6})


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


def validate_calendar_step(start_day: int, total_months: int) -> None:
    """Raise SafeValueError if *total_months* cannot be represented as a calendar spec.

    Args:
        start_day: Day-of-month of the interval's start datetime.
        total_months: Total months (years * 12 + months) in the duration.

    Raises:
        SafeValueError: If *total_months* cannot be represented as a calendar
            spec (e.g. 5, 7, or multi-year intervals), or if *start_day* is
            not valid for a sub-yearly monthly step (e.g. day 29-31).

    """
    if total_months < 12 and start_day > 28:  # noqa: PLR2004
        msg = (
            f"Day-of-month {start_day} is not valid for monthly schedules because "
            "not all months have that many days. Use a start date with day <= 28, "
            "or use a cron expression for more control."
        )
        raise SafeValueError(msg)

    if total_months == 12 or total_months in _REPRESENTABLE_MONTH_STEPS:  # noqa: PLR2004
        return

    msg = (
        f"Calendar interval of {total_months} months cannot be represented "
        "as a schedule. Use 1, 2, 3, 4, 6, or 12 months, or a cron expression."
    )
    raise SafeValueError(msg)


@dataclass(frozen=True)
class ParsedInterval:
    """Structured, Temporal-free result of parsing an ISO 8601 repeating interval.

    Exactly one of ``duration`` (fixed-length) or ``calendar_months``
    (calendar-based, from years/months) is set.
    """

    start_at: datetime
    end_at: datetime | None
    duration: timedelta | None
    calendar_months: int | None


def parse_iso8601_repeating_interval(interval: str) -> ParsedInterval:
    """Parse and fully validate an ISO 8601 repeating interval string.

    Supports formats:
    - ``R/<start>/<duration>`` — repeat indefinitely from start
    - ``R/<start>/<duration>/<end>`` — repeat from start until end

    Finite repetition counts (e.g. ``R1``, ``R5``) are not supported.
    Use an end date to limit the number of executions.

    Durations containing months or years (e.g. P1M, P1Y) must be
    representable as a calendar step (1, 2, 3, 4, 6, or 12 months) and may
    not be mixed with fixed components (days/hours/minutes/seconds).

    Args:
        interval: ISO 8601 repeating interval string.

    Returns:
        Structured, Temporal-free representation of the interval.

    Raises:
        SafeValueError: If the interval string is invalid.

    """
    match = _REPEATING_INTERVAL_PATTERN.match(interval)
    if not match:
        msg = f"Invalid ISO 8601 repeating interval: '{interval}'"
        raise SafeValueError(msg)

    repetitions_str, start_str, duration_str, end_str = match.groups()

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
        validate_calendar_step(start_at.day, total_months)
        return ParsedInterval(start_at=start_at, end_at=end_at, duration=None, calendar_months=total_months)

    duration = parse_iso8601_duration(duration_str)
    return ParsedInterval(start_at=start_at, end_at=end_at, duration=duration, calendar_months=None)


__all__ = [
    "ParsedInterval",
    "parse_iso8601_duration",
    "parse_iso8601_repeating_interval",
    "validate_calendar_step",
]
