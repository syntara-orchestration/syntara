"""Tests for ScheduledTriggerConfig model.

Covers:
- Valid configurations for each schedule type (interval, cron)
- Required field validation (interval required for interval type, cron for cron type)
- Cron expression format validation
- Timezone validation (IANA timezone names)
- MissedSchedulePolicy defaults
- Template expression rejection on schedule-shape fields
- Inactive schedule field (interval on a cron config, or vice versa) is not validated
"""

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import (
    MissedSchedulePolicy,
    ScheduledTriggerConfig,
    ScheduleType,
)


class TestValidConfigurations:
    """Tests for valid scheduled trigger configurations."""

    async def test_valid_cron_config(self) -> None:
        """Valid cron configuration should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
        )
        assert config.schedule_type == ScheduleType.CRON
        assert config.cron == "0 9 * * *"

    async def test_valid_cron_with_timezone(self) -> None:
        """Cron configuration with timezone should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            timezone="America/New_York",
        )
        assert config.timezone == "America/New_York"

    async def test_valid_cron_every_5_minutes(self) -> None:
        """Cron expression '*/5 * * * *' should be accepted (AAP-64513 E2E test)."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="*/5 * * * *",
        )
        assert config.cron == "*/5 * * * *"

    async def test_valid_interval_config(self) -> None:
        """Valid interval configuration should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.INTERVAL,
            interval="R/2024-01-01T10:00:00Z/P1D",
        )
        assert config.schedule_type == ScheduleType.INTERVAL
        assert config.interval == "R/2024-01-01T10:00:00Z/P1D"

    async def test_valid_interval_weekly(self) -> None:
        """Weekly interval should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.INTERVAL,
            interval="R/2024-01-01T00:00:00Z/P7D",
        )
        assert config.interval == "R/2024-01-01T00:00:00Z/P7D"

    async def test_valid_cron_with_ranges_and_lists(self) -> None:
        """Cron expression with ranges and lists should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9-17 * * 1,3,5",
        )
        assert config.cron == "0 9-17 * * 1,3,5"

    async def test_valid_cron_all_wildcards(self) -> None:
        """Cron expression '* * * * *' (every minute) should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="* * * * *",
        )
        assert config.cron == "* * * * *"


class TestMissedSchedulePolicy:
    """Tests for missed_schedule_policy field."""

    @pytest.mark.parametrize(
        "value",
        ["skip", "buffer_one", "buffer_all", "allow_all", "cancel_other"],
    )
    def test_enum_from_string(self, value: str) -> None:
        """Every policy string must round-trip through the StrEnum."""
        import importlib

        import syntara.workflows.workflow_engine.models.workflow_definition as mod

        importlib.reload(mod)
        reloaded = mod.MissedSchedulePolicy(value)
        assert reloaded.value == value

    async def test_defaults_to_skip(self) -> None:
        """missed_schedule_policy should default to 'skip'."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
        )
        assert config.missed_schedule_policy == MissedSchedulePolicy.SKIP

    async def test_buffer_one_accepted(self) -> None:
        """missed_schedule_policy 'buffer_one' should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            missed_schedule_policy=MissedSchedulePolicy.BUFFER_ONE,
        )
        assert config.missed_schedule_policy == MissedSchedulePolicy.BUFFER_ONE

    async def test_buffer_all_accepted(self) -> None:
        """missed_schedule_policy 'buffer_all' should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            missed_schedule_policy=MissedSchedulePolicy.BUFFER_ALL,
        )
        assert config.missed_schedule_policy == MissedSchedulePolicy.BUFFER_ALL

    async def test_allow_all_accepted(self) -> None:
        """missed_schedule_policy 'allow_all' should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            missed_schedule_policy=MissedSchedulePolicy.ALLOW_ALL,
        )
        assert config.missed_schedule_policy == MissedSchedulePolicy.ALLOW_ALL

    async def test_cancel_other_accepted(self) -> None:
        """missed_schedule_policy 'cancel_other' should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            missed_schedule_policy=MissedSchedulePolicy.CANCEL_OTHER,
        )
        assert config.missed_schedule_policy == MissedSchedulePolicy.CANCEL_OTHER


class TestRequiredFieldValidation:
    """Tests for conditional required field validation."""

    async def test_interval_required_for_interval_type(self) -> None:
        """Interval field is required when schedule_type is 'interval'."""
        with pytest.raises((ValidationError, ValueError)):
            ScheduledTriggerConfig(schedule_type=ScheduleType.INTERVAL)

    async def test_cron_required_for_cron_type(self) -> None:
        """Cron field is required when schedule_type is 'cron'."""
        with pytest.raises((ValidationError, ValueError)):
            ScheduledTriggerConfig(schedule_type=ScheduleType.CRON)

    async def test_interval_not_required_for_cron_type(self) -> None:
        """Interval field should not be required for cron type."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
        )
        assert config.interval is None

    async def test_cron_not_required_for_interval_type(self) -> None:
        """Cron field should not be required for interval type."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.INTERVAL,
            interval="R/2024-01-01T00:00:00Z/P1D",
        )
        assert config.cron is None


class TestCronExpressionValidation:
    """Tests for cron expression format validation."""

    async def test_rejects_6_field_cron(self) -> None:
        """6-field cron expressions should be rejected (only 5-field supported)."""
        with pytest.raises((ValidationError, ValueError)):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="0 0 9 * * *",
            )

    async def test_rejects_empty_cron(self) -> None:
        """Empty cron expression should be rejected."""
        with pytest.raises((ValidationError, ValueError)):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="",
            )

    async def test_rejects_invalid_cron_text(self) -> None:
        """Non-cron text should be rejected."""
        with pytest.raises((ValidationError, ValueError)):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="every day at 9am",
            )

    async def test_rejects_cron_with_special_chars(self) -> None:
        """Cron with special characters should be rejected."""
        with pytest.raises((ValidationError, ValueError)):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="0 9 * * @daily",
            )

    @pytest.mark.parametrize(
        ("cron", "bad_field"),
        [
            ("60 9 * * *", "minute"),
            ("0 24 * * *", "hour"),
            ("0 9 32 * *", "day-of-month"),
            ("0 9 0 * *", "day-of-month"),
            ("0 9 * 13 *", "month"),
            ("0 9 * 0 *", "month"),
            ("0 9 * * 8", "day-of-week"),
            ("99 99 99 99 99", "minute"),
        ],
    )
    async def test_rejects_cron_out_of_range(self, cron: str, bad_field: str) -> None:
        """Cron values outside allowed ranges should be rejected with a specific message."""
        with pytest.raises((ValidationError, ValueError), match=bad_field):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron=cron,
            )


class TestTimezoneValidation:
    """Tests for timezone field validation."""

    async def test_valid_timezone_utc(self) -> None:
        """UTC timezone should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            timezone="UTC",
        )
        assert config.timezone == "UTC"

    async def test_valid_timezone_us_eastern(self) -> None:
        """America/New_York timezone should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            timezone="America/New_York",
        )
        assert config.timezone == "America/New_York"

    async def test_valid_timezone_europe(self) -> None:
        """Europe/London timezone should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            timezone="Europe/London",
        )
        assert config.timezone == "Europe/London"

    async def test_rejects_invalid_timezone(self) -> None:
        """Invalid timezone names should be rejected."""
        with pytest.raises((ValidationError, ValueError)):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="0 9 * * *",
                timezone="Invalid/Timezone",
            )

    async def test_rejects_nonexistent_timezone(self) -> None:
        """Non-existent timezone names should be rejected."""
        with pytest.raises((ValidationError, ValueError)):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="0 9 * * *",
                timezone="US/FakeCity",
            )

    async def test_timezone_defaults_to_none(self) -> None:
        """Timezone should default to None (UTC is applied by the scheduler)."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
        )
        assert config.timezone is None

    async def test_valid_timezones_is_nonempty(self) -> None:
        """Regression: available timezone set must never be empty (AAP-86297)."""
        from syntara.workflows.workflow_engine.models.workflow_definition import (
            _get_valid_timezones,
        )

        tzs = _get_valid_timezones()
        assert len(tzs) > 100, f"Expected >100 timezones, got {len(tzs)}"
        assert "America/New_York" in tzs
        assert "Europe/London" in tzs
        assert "UTC" in tzs

    async def test_raises_when_no_timezone_data(self) -> None:
        """Runtime guard should raise if timezone data is missing (AAP-86297)."""
        from unittest.mock import patch

        import syntara.workflows.workflow_engine.models.workflow_definition as wd

        original = wd._VALID_TIMEZONES
        try:
            wd._VALID_TIMEZONES = None  # Force re-initialisation
            with (
                patch.object(wd, "available_timezones", return_value=frozenset()),
                pytest.raises(RuntimeError, match="No IANA timezone data found"),
            ):
                wd._get_valid_timezones()
        finally:
            wd._VALID_TIMEZONES = original

    async def test_published_workflow_timezone_round_trip(self) -> None:
        """Timezone selected from a standard dropdown must survive validation (AAP-86297)."""
        browser_timezones = [
            "America/New_York",
            "America/Chicago",
            "America/Los_Angeles",
            "Europe/London",
            "Asia/Tokyo",
            "Australia/Sydney",
            "Pacific/Auckland",
        ]
        for tz in browser_timezones:
            config = ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="0 9 * * *",
                timezone=tz,
            )
            assert config.timezone == tz, f"Timezone {tz} should be accepted"


class TestIntervalValidation:
    """Tests for interval field validation at the model layer.

    ``interval`` previously had no semantic validation beyond "non-empty",
    so ``ScheduledTriggerConfig.model_validate`` (used by ``/workflows/validate``,
    publish, and Temporal sync) accepted malformed intervals that only failed
    later in ``schedule_parser.parse_iso8601_interval`` — after publish had
    already committed. These tests lock the same semantics at the model layer.
    """

    async def test_valid_daily_interval(self) -> None:
        """Daily interval should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.INTERVAL,
            interval="R/2024-01-01T10:00:00Z/P1D",
        )
        assert config.interval == "R/2024-01-01T10:00:00Z/P1D"

    async def test_valid_interval_with_end_date(self) -> None:
        """Interval with an end date should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.INTERVAL,
            interval="R/2024-01-01T10:00:00Z/P1D/2024-12-31T23:59:59Z",
        )
        assert config.interval == "R/2024-01-01T10:00:00Z/P1D/2024-12-31T23:59:59Z"

    async def test_valid_monthly_interval(self) -> None:
        """Calendar-representable monthly interval (P1M) should be accepted."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.INTERVAL,
            interval="R/2024-01-15T09:00:00Z/P1M",
        )
        assert config.interval == "R/2024-01-15T09:00:00Z/P1M"

    async def test_rejects_not_an_interval(self) -> None:
        """Non-interval text should be rejected."""
        with pytest.raises((ValidationError, ValueError), match="Invalid ISO 8601 repeating interval"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.INTERVAL,
                interval="not-an-interval",
            )

    async def test_rejects_finite_repetition_count(self) -> None:
        """Finite repetition counts (e.g. R1/...) should be rejected."""
        with pytest.raises((ValidationError, ValueError), match="not supported"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.INTERVAL,
                interval="R1/2024-01-01T10:00:00Z/P1D",
            )

    async def test_rejects_start_datetime_without_timezone(self) -> None:
        """Start datetime lacking timezone info should be rejected."""
        with pytest.raises((ValidationError, ValueError), match="timezone info"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.INTERVAL,
                interval="R/2024-01-01T10:00:00/P1D",
            )

    async def test_rejects_invalid_duration(self) -> None:
        """Malformed ISO 8601 duration (starts with P but invalid shape) should be rejected."""
        with pytest.raises((ValidationError, ValueError), match="Invalid ISO 8601 duration"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.INTERVAL,
                interval="R/2024-01-01T10:00:00Z/PXYZ",
            )

    async def test_rejects_mixed_calendar_and_fixed_duration(self) -> None:
        """Mixed calendar (months) and fixed (days) components should be rejected."""
        with pytest.raises((ValidationError, ValueError), match="Mixed calendar and fixed"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.INTERVAL,
                interval="R/2024-01-01T00:00:00Z/P1M2D",
            )

    async def test_rejects_unrepresentable_month_step(self) -> None:
        """Month steps that cannot be expressed as a calendar spec (e.g. P5M) should be rejected."""
        with pytest.raises((ValidationError, ValueError), match="cannot be represented"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.INTERVAL,
                interval="R/2024-01-01T00:00:00Z/P5M",
            )

    async def test_rejects_day_29_monthly(self) -> None:
        """Day-of-month 29 with a monthly interval should be rejected."""
        with pytest.raises((ValidationError, ValueError), match="Day-of-month 29"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.INTERVAL,
                interval="R/2024-01-29T10:00:00Z/P1M",
            )

    async def test_interval_none_passes(self) -> None:
        """interval=None (e.g. cron schedule_type) should bypass validation."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
        )
        assert config.interval is None


class TestTemplateScheduleFieldsRejected:
    """Schedule-shape fields (schedule_type/interval/cron/timezone) reject templates.

    Unlike other node parameters, these fields are materialized into a
    Temporal Schedule once at publish time -- there is no runtime execution
    context to resolve ``${...}`` against later. Letting the generic
    TemplateAwareBaseModel bypass wave these through would let verify and
    pre-mutation publish accept a config that can never become a schedule,
    then fail post-commit in ``config_to_temporal_schedule``.
    """

    async def test_template_cron_is_rejected(self) -> None:
        """Template expression in cron field is rejected, not bypassed."""
        with pytest.raises(ValidationError, match="does not support template expressions"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="${input.cron_expression}",
            )

    async def test_template_timezone_is_rejected(self) -> None:
        """Template expression in timezone field is rejected, not bypassed."""
        with pytest.raises(ValidationError, match="does not support template expressions"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.CRON,
                cron="0 9 * * *",
                timezone="${input.timezone}",
            )

    async def test_template_schedule_type_is_rejected(self) -> None:
        """Template expression in schedule_type field is rejected, not bypassed."""
        with pytest.raises(ValidationError, match="does not support template expressions"):
            ScheduledTriggerConfig(
                schedule_type="${input.schedule_type}",  # type: ignore[arg-type]
            )

    async def test_template_interval_is_rejected(self) -> None:
        """Template expression in interval field is rejected, not bypassed."""
        with pytest.raises(ValidationError, match="does not support template expressions"):
            ScheduledTriggerConfig(
                schedule_type=ScheduleType.INTERVAL,
                interval="${input.interval}",
            )


class TestInactiveScheduleFieldIgnored:
    """The field that doesn't match schedule_type is not validated.

    ``config_to_temporal_schedule`` only ever reads ``interval`` for an
    interval schedule and ``cron`` for a cron schedule, so a stale/invalid
    leftover value in the inactive field (e.g. left over from switching
    schedule_type in the Builder) must not block verify or publish.
    """

    async def test_invalid_interval_ignored_when_schedule_type_is_cron(self) -> None:
        """An invalid interval string does not block a cron config."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            interval="not-an-interval",
        )
        assert config.interval == "not-an-interval"

    async def test_invalid_cron_ignored_when_schedule_type_is_interval(self) -> None:
        """An invalid cron string does not block an interval config."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.INTERVAL,
            interval="R/2024-01-01T10:00:00Z/P1D",
            cron="not-a-cron",
        )
        assert config.cron == "not-a-cron"
