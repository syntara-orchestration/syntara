"""Tests for schedule_parser utility.

Covers:
- ISO 8601 duration parsing (P1D, P7D, P1M, P1Y, compound)
- ISO 8601 repeating interval parsing (start, duration, end date)
- Cron expression to ScheduleSpec conversion
- Missed schedule policy to SchedulePolicy mapping
- config_to_temporal_schedule dispatch
- Deterministic schedule ID generation
- Edge cases and error handling
"""

from datetime import UTC, datetime, timedelta

import pytest
from temporalio.client import ScheduleOverlapPolicy, ScheduleRange

from syntara.core.exceptions import SafeValueError
from syntara.workflows.utils.schedule_parser import (
    _interval_to_calendar_spec,
    build_schedule_id,
    build_schedule_policy,
    config_to_temporal_schedule,
    parse_cron_to_spec,
    parse_iso8601_duration,
    parse_iso8601_interval,
)
from syntara.workflows.workflow_engine.models.workflow_definition import MissedSchedulePolicy


class TestParseISO8601Duration:
    """Tests for ISO 8601 duration parsing."""

    async def test_parse_one_day(self) -> None:
        """P1D should parse to 1 day."""
        assert parse_iso8601_duration("P1D") == timedelta(days=1)

    async def test_parse_one_week(self) -> None:
        """P7D should parse to 7 days."""
        assert parse_iso8601_duration("P7D") == timedelta(days=7)

    async def test_parse_one_week_via_weeks(self) -> None:
        """P1W should parse to 7 days."""
        assert parse_iso8601_duration("P1W") == timedelta(weeks=1)

    async def test_rejects_months(self) -> None:
        """P1M should be rejected — months can't be a fixed timedelta."""
        with pytest.raises(SafeValueError, match="months or years"):
            parse_iso8601_duration("P1M")

    async def test_rejects_years(self) -> None:
        """P1Y should be rejected — years can't be a fixed timedelta."""
        with pytest.raises(SafeValueError, match="months or years"):
            parse_iso8601_duration("P1Y")

    async def test_rejects_months_with_days(self) -> None:
        """P1M5D should be rejected — months can't be a fixed timedelta."""
        with pytest.raises(SafeValueError, match="months or years"):
            parse_iso8601_duration("P1M5D")

    async def test_parse_one_hour(self) -> None:
        """PT1H should parse to 1 hour."""
        assert parse_iso8601_duration("PT1H") == timedelta(hours=1)

    async def test_parse_thirty_minutes(self) -> None:
        """PT30M should parse to 30 minutes."""
        assert parse_iso8601_duration("PT30M") == timedelta(minutes=30)

    async def test_parse_compound(self) -> None:
        """P1DT12H30M should parse to 1 day + 12h + 30m."""
        result = parse_iso8601_duration("P1DT12H30M")
        expected = timedelta(days=1, hours=12, minutes=30)
        assert result == expected

    async def test_rejects_invalid_duration(self) -> None:
        """Invalid duration string should raise SafeValueError."""
        with pytest.raises(SafeValueError):
            parse_iso8601_duration("not-a-duration")

    async def test_rejects_zero_duration(self) -> None:
        """Zero duration (P0D / PT0S) should raise SafeValueError."""
        with pytest.raises(SafeValueError):
            parse_iso8601_duration("PT0S")

    async def test_rejects_empty_p(self) -> None:
        """Bare 'P' should raise SafeValueError."""
        with pytest.raises(SafeValueError):
            parse_iso8601_duration("P")


class TestParseISO8601Interval:
    """Tests for ISO 8601 repeating interval parsing."""

    async def test_parse_daily_interval(self) -> None:
        """Daily interval should produce spec with 1-day interval."""
        spec = parse_iso8601_interval("R/2024-01-01T10:00:00Z/P1D")
        assert len(spec.intervals) == 1
        assert spec.intervals[0].every == timedelta(days=1)
        assert spec.start_at is not None

    async def test_parse_weekly_interval(self) -> None:
        """Weekly interval should produce spec with 7-day interval."""
        spec = parse_iso8601_interval("R/2024-01-01T00:00:00Z/P7D")
        assert spec.intervals[0].every == timedelta(days=7)

    async def test_parse_interval_with_end_date(self) -> None:
        """Interval with end date should set end_at."""
        spec = parse_iso8601_interval("R/2024-01-01T10:00:00Z/P1D/2024-12-31T23:59:59Z")
        assert spec.end_at is not None

    async def test_parse_interval_without_end_date(self) -> None:
        """Interval without end date should have end_at=None."""
        spec = parse_iso8601_interval("R/2024-01-01T10:00:00Z/P1D")
        assert spec.end_at is None

    async def test_parse_interval_with_timezone(self) -> None:
        """Timezone should be set on the spec."""
        spec = parse_iso8601_interval("R/2024-01-01T10:00:00Z/P1D", tz="America/New_York")
        assert spec.time_zone_name == "America/New_York"

    async def test_parse_interval_defaults_to_utc(self) -> None:
        """Default timezone should be UTC."""
        spec = parse_iso8601_interval("R/2024-01-01T10:00:00Z/P1D")
        assert spec.time_zone_name == "UTC"

    async def test_finite_repetition_rejected(self) -> None:
        """Finite repetition counts are not supported."""
        with pytest.raises(SafeValueError, match="not supported"):
            parse_iso8601_interval("R1/2024-01-01T10:00:00Z/P1D")

    async def test_mixed_calendar_duration_rejected(self) -> None:
        """P1Y2M (14 months) should be rejected as unrepresentable."""
        with pytest.raises(SafeValueError, match="cannot be represented"):
            parse_iso8601_interval("R/2024-01-01T00:00:00Z/P1Y2M")

    async def test_rejects_mixed_months_and_days(self) -> None:
        """P1M2D should be rejected — mixed calendar and fixed components."""
        with pytest.raises(SafeValueError, match="Mixed calendar and fixed"):
            parse_iso8601_interval("R/2024-01-01T00:00:00Z/P1M2D")

    async def test_rejects_mixed_months_days_hours(self) -> None:
        """P1M2DT4H should be rejected — days and hours silently dropped."""
        with pytest.raises(SafeValueError, match="Mixed calendar and fixed"):
            parse_iso8601_interval("R/2024-01-01T00:00:00Z/P1M2DT4H")

    async def test_rejects_mixed_months_and_minutes(self) -> None:
        """P1MT30M should be rejected — minutes silently dropped."""
        with pytest.raises(SafeValueError, match="Mixed calendar and fixed"):
            parse_iso8601_interval("R/2024-01-01T00:00:00Z/P1MT30M")

    async def test_rejects_invalid_interval(self) -> None:
        """Invalid interval string should raise SafeValueError."""
        with pytest.raises(SafeValueError):
            parse_iso8601_interval("not-an-interval")


class TestParseCronToSpec:
    """Tests for cron expression to ScheduleSpec conversion."""

    async def test_basic_cron(self) -> None:
        """Cron expression should be passed to spec."""
        spec = parse_cron_to_spec("0 9 * * *")
        assert spec.cron_expressions == ["0 9 * * *"]

    async def test_cron_with_timezone(self) -> None:
        """Timezone should be set on the spec."""
        spec = parse_cron_to_spec("0 9 * * *", tz="Europe/London")
        assert spec.time_zone_name == "Europe/London"

    async def test_cron_defaults_to_utc(self) -> None:
        """Default timezone should be UTC."""
        spec = parse_cron_to_spec("*/5 * * * *")
        assert spec.time_zone_name == "UTC"

    async def test_cron_every_5_minutes(self) -> None:
        """Every-5-minutes cron should be accepted (AAP-64513 E2E test)."""
        spec = parse_cron_to_spec("*/5 * * * *", tz="America/New_York")
        assert spec.cron_expressions == ["*/5 * * * *"]
        assert spec.time_zone_name == "America/New_York"


class TestBuildSchedulePolicy:
    """Tests for missed schedule policy mapping."""

    async def test_skip_policy(self) -> None:
        """Skip policy should use SKIP overlap and short catchup window."""
        policy = build_schedule_policy(MissedSchedulePolicy.SKIP)
        assert policy.overlap == ScheduleOverlapPolicy.SKIP
        assert policy.catchup_window == timedelta(seconds=1)

    async def test_buffer_one_policy(self) -> None:
        """Buffer-one policy should use BUFFER_ONE overlap and 48h catchup window."""
        policy = build_schedule_policy(MissedSchedulePolicy.BUFFER_ONE)
        assert policy.overlap == ScheduleOverlapPolicy.BUFFER_ONE
        assert policy.catchup_window == timedelta(hours=48)

    async def test_buffer_all_policy(self) -> None:
        """Buffer-all policy should use BUFFER_ALL overlap and 48h catchup window."""
        policy = build_schedule_policy(MissedSchedulePolicy.BUFFER_ALL)
        assert policy.overlap == ScheduleOverlapPolicy.BUFFER_ALL
        assert policy.catchup_window == timedelta(hours=48)

    async def test_allow_all_policy(self) -> None:
        """Allow-all policy should use ALLOW_ALL overlap and 48h catchup window."""
        policy = build_schedule_policy(MissedSchedulePolicy.ALLOW_ALL)
        assert policy.overlap == ScheduleOverlapPolicy.ALLOW_ALL
        assert policy.catchup_window == timedelta(hours=48)

    async def test_cancel_other_policy(self) -> None:
        """Cancel-other policy should use CANCEL_OTHER overlap and short catchup window."""
        policy = build_schedule_policy(MissedSchedulePolicy.CANCEL_OTHER)
        assert policy.overlap == ScheduleOverlapPolicy.CANCEL_OTHER
        assert policy.catchup_window == timedelta(seconds=1)

    async def test_string_policy_values(self) -> None:
        """String policy values should work via StrEnum coercion."""
        policy = build_schedule_policy(MissedSchedulePolicy("skip"))
        assert policy.overlap == ScheduleOverlapPolicy.SKIP

    def test_all_enum_members_have_mapping(self) -> None:
        """build_schedule_policy must handle every MissedSchedulePolicy member."""
        for policy in MissedSchedulePolicy:
            result = build_schedule_policy(policy)
            assert result.overlap is not None


class TestBuildScheduleId:
    """Tests for deterministic schedule ID generation."""

    async def test_basic_id(self) -> None:
        """Schedule ID should follow convention."""
        schedule_id = build_schedule_id("abc-123", "trigger_1")
        assert schedule_id == "orchestrator-sched-abc-123-trigger_1"

    async def test_id_is_deterministic(self) -> None:
        """Same inputs should always produce the same ID."""
        id1 = build_schedule_id("wf-id", "node-id")
        id2 = build_schedule_id("wf-id", "node-id")
        assert id1 == id2


class TestConfigToTemporalSchedule:
    """Tests for config_to_temporal_schedule dispatch."""

    async def test_cron_config(self) -> None:
        """Cron config should produce cron-based spec."""
        spec, policy = config_to_temporal_schedule(
            {
                "schedule_type": "cron",
                "cron": "0 9 * * *",
                "timezone": "UTC",
            }
        )
        assert spec.cron_expressions == ["0 9 * * *"]
        assert policy.overlap == ScheduleOverlapPolicy.SKIP

    async def test_interval_config(self) -> None:
        """Interval config should produce interval-based spec."""
        spec, _policy = config_to_temporal_schedule(
            {
                "schedule_type": "interval",
                "interval": "R/2024-01-01T00:00:00Z/P1D",
            }
        )
        assert len(spec.intervals) == 1
        assert spec.intervals[0].every == timedelta(days=1)

    @pytest.mark.parametrize(
        ("policy_value", "expected_overlap"),
        [
            ("skip", ScheduleOverlapPolicy.SKIP),
            ("buffer_one", ScheduleOverlapPolicy.BUFFER_ONE),
            ("buffer_all", ScheduleOverlapPolicy.BUFFER_ALL),
            ("allow_all", ScheduleOverlapPolicy.ALLOW_ALL),
            ("cancel_other", ScheduleOverlapPolicy.CANCEL_OTHER),
        ],
    )
    async def test_all_policies_pass_through_config(
        self, policy_value: str, expected_overlap: ScheduleOverlapPolicy
    ) -> None:
        """Every MissedSchedulePolicy value must produce the correct Temporal overlap policy."""
        _spec, policy = config_to_temporal_schedule(
            {
                "schedule_type": "cron",
                "cron": "0 9 * * *",
                "missed_schedule_policy": policy_value,
            }
        )
        assert policy.overlap == expected_overlap

    async def test_rejects_unknown_schedule_type(self) -> None:
        """Unknown schedule_type should raise SafeValueError."""
        with pytest.raises(SafeValueError):
            config_to_temporal_schedule({"schedule_type": "hourly"})

    async def test_rejects_missing_interval(self) -> None:
        """Interval type without interval field should raise SafeValueError."""
        with pytest.raises(SafeValueError):
            config_to_temporal_schedule({"schedule_type": "interval"})

    async def test_rejects_missing_cron(self) -> None:
        """Cron type without cron field should raise SafeValueError."""
        with pytest.raises(SafeValueError):
            config_to_temporal_schedule({"schedule_type": "cron"})

    async def test_defaults_missed_policy_to_skip(self) -> None:
        """Missing missed_schedule_policy should default to SKIP overlap."""
        _spec, policy = config_to_temporal_schedule(
            {
                "schedule_type": "cron",
                "cron": "0 9 * * *",
            }
        )
        assert policy.overlap == ScheduleOverlapPolicy.SKIP


class TestIntervalToCalendarSpec:
    """Tests for _interval_to_calendar_spec calendar-interval conversion."""

    async def test_monthly_interval(self) -> None:
        """P1M from Jan 15 at 10:30 → fires day 15, every month."""
        start = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        cal = _interval_to_calendar_spec(start, total_months=1)
        assert cal.minute == [ScheduleRange(30)]
        assert cal.hour == [ScheduleRange(10)]
        assert cal.day_of_month == [ScheduleRange(15)]
        assert cal.month == [ScheduleRange(1, 12)]

    async def test_quarterly_interval(self) -> None:
        """P3M from Jan 1 at midnight → fires day 1, every 3 months."""
        start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        cal = _interval_to_calendar_spec(start, total_months=3)
        assert cal.day_of_month == [ScheduleRange(1)]
        assert cal.month == [ScheduleRange(1, 12, step=3)]

    async def test_quarterly_offset(self) -> None:
        """P3M from May → offset 2, fires months 2, 5, 8, 11."""
        start = datetime(2024, 5, 1, 0, 0, tzinfo=UTC)
        cal = _interval_to_calendar_spec(start, total_months=3)
        assert cal.month == [ScheduleRange(2, 12, step=3)]

    async def test_yearly_interval(self) -> None:
        """P1Y from Mar 1 at 9:00 → fires Mar 1 each year."""
        start = datetime(2024, 3, 1, 9, 0, tzinfo=UTC)
        cal = _interval_to_calendar_spec(start, total_months=12)
        assert cal.minute == [ScheduleRange(0)]
        assert cal.hour == [ScheduleRange(9)]
        assert cal.day_of_month == [ScheduleRange(1)]
        assert cal.month == [ScheduleRange(3)]

    async def test_biannual_interval(self) -> None:
        """P6M from Jun 15 at 14:00 → fires day 15, every 6 months."""
        start = datetime(2024, 6, 15, 14, 0, tzinfo=UTC)
        cal = _interval_to_calendar_spec(start, total_months=6)
        assert cal.day_of_month == [ScheduleRange(15)]
        assert cal.month == [ScheduleRange(6, 12, step=6)]

    async def test_bimonthly_interval(self) -> None:
        """P2M from Mar → offset 1, fires months 1, 3, 5, 7, 9, 11."""
        start = datetime(2024, 3, 10, 8, 0, tzinfo=UTC)
        cal = _interval_to_calendar_spec(start, total_months=2)
        assert cal.month == [ScheduleRange(1, 12, step=2)]

    async def test_rejects_day_29_monthly(self) -> None:
        """Day 29 with monthly interval is rejected — Feb has 28 days in common years."""
        start = datetime(2024, 1, 29, 10, 0, tzinfo=UTC)
        with pytest.raises(SafeValueError, match="Day-of-month 29"):
            _interval_to_calendar_spec(start, total_months=1)

    async def test_rejects_day_31_monthly(self) -> None:
        """Day 31 with monthly interval is rejected — many months lack day 31."""
        start = datetime(2024, 1, 31, 10, 0, tzinfo=UTC)
        with pytest.raises(SafeValueError, match="Day-of-month 31"):
            _interval_to_calendar_spec(start, total_months=3)

    async def test_day_28_monthly_accepted(self) -> None:
        """Day 28 with monthly interval is accepted — all months have 28 days."""
        start = datetime(2024, 1, 28, 10, 0, tzinfo=UTC)
        cal = _interval_to_calendar_spec(start, total_months=1)
        assert cal.day_of_month == [ScheduleRange(28)]

    async def test_day_31_yearly_accepted(self) -> None:
        """Day 31 with yearly interval is accepted — fires in a specific month."""
        start = datetime(2024, 1, 31, 9, 0, tzinfo=UTC)
        cal = _interval_to_calendar_spec(start, total_months=12)
        assert cal.day_of_month == [ScheduleRange(31)]
        assert cal.month == [ScheduleRange(1)]

    async def test_rejects_unrepresentable_months(self) -> None:
        """P5M, P7M, etc. cannot be expressed as a calendar spec."""
        start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        for months in (5, 7, 8, 9, 10, 11):
            with pytest.raises(SafeValueError, match="cannot be represented"):
                _interval_to_calendar_spec(start, total_months=months)

    async def test_rejects_multi_year(self) -> None:
        """P2Y (24 months) cannot be expressed as a calendar spec."""
        start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        with pytest.raises(SafeValueError, match="cannot be represented"):
            _interval_to_calendar_spec(start, total_months=24)

    async def test_calendar_interval_in_parse_iso8601(self) -> None:
        """Monthly interval should produce calendar-based spec, not timedelta."""
        spec = parse_iso8601_interval("R/2024-03-01T09:00:00Z/P1M")
        assert len(spec.calendars) == 1
        assert spec.calendars[0].month == [ScheduleRange(1, 12)]
        assert len(spec.intervals) == 0
        assert len(spec.cron_expressions) == 0
