"""Tests for ScheduledTriggerConfig model.

Covers:
- Valid configurations for each schedule type (interval, cron)
- Required field validation (interval required for interval type, cron for cron type)
- Cron expression format validation
- Timezone validation (IANA timezone names)
- MissedSchedulePolicy defaults
- Template expression bypass
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


class TestTemplateExpressionBypass:
    """Tests for template expression bypass in validated fields."""

    async def test_template_cron_bypasses_validation(self) -> None:
        """Template expression in cron field should bypass validation."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="${input.cron_expression}",
        )
        assert config.cron == "${input.cron_expression}"

    async def test_template_timezone_bypasses_validation(self) -> None:
        """Template expression in timezone field should bypass validation."""
        config = ScheduledTriggerConfig(
            schedule_type=ScheduleType.CRON,
            cron="0 9 * * *",
            timezone="${input.timezone}",
        )
        assert config.timezone == "${input.timezone}"

    async def test_template_schedule_type_bypasses_required_check(self) -> None:
        """Template expression in schedule_type should bypass required field checks."""
        config = ScheduledTriggerConfig(
            schedule_type="${input.schedule_type}",  # type: ignore[arg-type]
        )
        assert config.schedule_type == "${input.schedule_type}"
