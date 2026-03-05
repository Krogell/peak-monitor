"""Unit tests for weekend start/end hour behaviour."""
import pytest
from unittest.mock import Mock
from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import (
    ACTIVE_STATE_OFF,
    ACTIVE_STATE_ON,
    ACTIVE_STATE_REDUCED,
    BEHAVIOR_NO_TARIFF,
    BEHAVIOR_REDUCED_TARIFF,
    BEHAVIOR_FULL_TARIFF,
)

TZ = ZoneInfo("Europe/Stockholm")


def _make_coordinator(
    weekend_behavior: str = BEHAVIOR_NO_TARIFF,
    weekend_start_hour: int = 6,
    weekend_end_hour: int = 21,
    active_start_hour: int = 6,
    active_end_hour: int = 21,
    active_months: list | None = None,
) -> PeakMonitorCoordinator:
    """Create a coordinator configured for weekend hour tests."""
    if active_months is None:
        active_months = list(range(1, 13))  # All months active

    mock_entry = Mock()
    mock_entry.entry_id = "test_weekend"
    mock_entry.data = {
        "consumption_sensor": "sensor.power",
        "sensor_resets_every_hour": True,
        "active_start_hour": active_start_hour,
        "active_end_hour": active_end_hour,
        "active_months": [str(m) for m in active_months],
        "number_of_peaks": 3,
        "only_one_peak_per_day": True,
        "holidays": [],
        "holiday_behavior": BEHAVIOR_NO_TARIFF,
        "weekend_behavior": weekend_behavior,
        "weekend_start_hour": weekend_start_hour,
        "weekend_end_hour": weekend_end_hour,
        "reset_value": 500,
        "price_per_kw": 0,
        "fixed_monthly_fee": 0,
        "output_unit": "W",
        "daily_reduced_tariff_enabled": False,
        "reduced_start_hour": 21,
        "reduced_end_hour": 6,
        "reduced_factor": 0.5,
    }
    mock_entry.options = {}

    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states.get = Mock(return_value=None)

    return PeakMonitorCoordinator(mock_hass, mock_entry)


def _saturday(hour: int) -> datetime:
    """Return a Saturday at the given hour (2025-02-01 is a Saturday)."""
    return datetime(2025, 2, 1, hour, 0, 0, tzinfo=TZ)


def _sunday(hour: int) -> datetime:
    """Return a Sunday at the given hour (2025-02-02 is a Sunday)."""
    return datetime(2025, 2, 2, hour, 0, 0, tzinfo=TZ)


def _weekday(hour: int) -> datetime:
    """Return a weekday (Monday) at the given hour (2025-02-03 is a Monday)."""
    return datetime(2025, 2, 3, hour, 0, 0, tzinfo=TZ)


# ---------------------------------------------------------------------------
# Basic weekend interval enforcement
# ---------------------------------------------------------------------------

class TestWeekendHoursNoTariff:
    """Weekend behaviour = no_tariff with a defined time window."""

    def test_inside_window_is_off(self):
        """Weekend no_tariff inside the interval → ACTIVE_STATE_OFF."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        state = coord.get_tariff_active_state(_saturday(10))
        assert state == ACTIVE_STATE_OFF

    def test_outside_window_before_start_is_off(self):
        """Before weekend interval starts → tariff inactive (time_of_day)."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        state = coord.get_tariff_active_state(_saturday(4))
        assert state == ACTIVE_STATE_OFF

    def test_outside_window_after_end_is_off(self):
        """After weekend interval ends → tariff inactive (time_of_day)."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        state = coord.get_tariff_active_state(_saturday(22))
        assert state == ACTIVE_STATE_OFF


class TestWeekendHoursReducedTariff:
    """Weekend behaviour = reduced_tariff with a defined time window."""

    def test_inside_window_is_reduced(self):
        """Weekend reduced_tariff inside interval → ACTIVE_STATE_REDUCED."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_REDUCED_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        state = coord.get_tariff_active_state(_saturday(12))
        assert state == ACTIVE_STATE_REDUCED

    def test_outside_window_is_off(self):
        """Weekend reduced_tariff outside interval → ACTIVE_STATE_OFF."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_REDUCED_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        state = coord.get_tariff_active_state(_saturday(22))
        assert state == ACTIVE_STATE_OFF

    def test_sunday_inside_window_is_reduced(self):
        """Sunday inside interval with reduced_tariff → ACTIVE_STATE_REDUCED."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_REDUCED_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        state = coord.get_tariff_active_state(_sunday(14))
        assert state == ACTIVE_STATE_REDUCED


class TestWeekendHoursFullTariff:
    """Weekend behaviour = full_tariff — weekday hour logic applies inside window."""

    def test_inside_weekend_window_and_active_hours_is_on(self):
        """Full tariff weekend inside interval and inside active hours → ON."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_FULL_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
            active_start_hour=6,
            active_end_hour=21,
        )
        state = coord.get_tariff_active_state(_saturday(10))
        assert state == ACTIVE_STATE_ON

    def test_outside_weekend_window_is_off(self):
        """Full tariff weekend outside interval → OFF regardless of active hours."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_FULL_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
            active_start_hour=6,
            active_end_hour=21,
        )
        state = coord.get_tariff_active_state(_saturday(22))
        assert state == ACTIVE_STATE_OFF


# ---------------------------------------------------------------------------
# Equal start/end hour → full day active
# ---------------------------------------------------------------------------

class TestWeekendHoursEqualStartEnd:
    """When weekend_start_hour == weekend_end_hour, the full day is covered."""

    def test_full_day_no_tariff_midnight(self):
        """With equal hours, no_tariff applies even at midnight."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=6,  # Equal → full day
        )
        assert coord.get_tariff_active_state(_saturday(0)) == ACTIVE_STATE_OFF
        assert coord.get_tariff_active_state(_saturday(6)) == ACTIVE_STATE_OFF
        assert coord.get_tariff_active_state(_saturday(23)) == ACTIVE_STATE_OFF

    def test_full_day_reduced_tariff(self):
        """With equal hours, reduced_tariff applies all day."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_REDUCED_TARIFF,
            weekend_start_hour=0,
            weekend_end_hour=0,  # Equal → full day
        )
        assert coord.get_tariff_active_state(_saturday(3)) == ACTIVE_STATE_REDUCED
        assert coord.get_tariff_active_state(_saturday(15)) == ACTIVE_STATE_REDUCED


# ---------------------------------------------------------------------------
# Boundary hours
# ---------------------------------------------------------------------------

class TestWeekendHoursBoundaries:
    """Test behaviour exactly at the boundary hours."""

    def test_at_start_hour_is_inside(self):
        """The start hour itself is considered inside the interval."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        assert coord.get_tariff_active_state(_saturday(6)) == ACTIVE_STATE_OFF

    def test_one_hour_before_start_is_outside(self):
        """One hour before start is outside the interval."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        assert coord.get_tariff_active_state(_saturday(5)) == ACTIVE_STATE_OFF

    def test_at_end_hour_is_outside(self):
        """At the end hour, the interval is considered closed — tariff is OFF."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        # is_time_in_range: end hour is exclusive
        state = coord.get_tariff_active_state(_saturday(21))
        assert state == ACTIVE_STATE_OFF


# ---------------------------------------------------------------------------
# Weekdays are not affected by weekend hours
# ---------------------------------------------------------------------------

class TestWeekdayUnaffectedByWeekendHours:
    """Weekday behaviour must not be influenced by weekend_start/end_hour."""

    def test_weekday_uses_normal_hours(self):
        """Monday inside active hours → ON, regardless of weekend config."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
            active_start_hour=6,
            active_end_hour=21,
        )
        assert coord.get_tariff_active_state(_weekday(10)) == ACTIVE_STATE_ON

    def test_weekday_outside_active_hours_is_off(self):
        """Monday outside active hours → OFF."""
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
            active_start_hour=6,
            active_end_hour=21,
        )
        assert coord.get_tariff_active_state(_weekday(22)) == ACTIVE_STATE_OFF


# ---------------------------------------------------------------------------
# Reason reporting
# ---------------------------------------------------------------------------

class TestWeekendHoursReasons:
    """Verify the reason codes returned by get_tariff_active_state_with_reasons."""

    def test_inside_window_no_tariff_reason_is_weekend(self):
        """Inside interval with no_tariff → reason includes REASON_WEEKEND."""
        from custom_components.peak_monitor.const import REASON_WEEKEND
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        state, reasons = coord.get_tariff_active_state_with_reasons(_saturday(10))
        assert state == ACTIVE_STATE_OFF
        assert REASON_WEEKEND in reasons

    def test_outside_window_reason_is_time_of_day(self):
        """Outside interval on a weekend → reason is time_of_day, not weekend."""
        from custom_components.peak_monitor.const import REASON_TIME_OF_DAY
        coord = _make_coordinator(
            weekend_behavior=BEHAVIOR_NO_TARIFF,
            weekend_start_hour=6,
            weekend_end_hour=21,
        )
        state, reasons = coord.get_tariff_active_state_with_reasons(_saturday(22))
        assert state == ACTIVE_STATE_OFF
        assert REASON_TIME_OF_DAY in reasons
