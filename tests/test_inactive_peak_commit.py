"""Tests for inactive-hours peak commit bug fix.

Verifies that:
1. Multiple-peaks-per-day mode does NOT commit hourly consumption when the
   tariff was inactive during that hour.
2. Multiple-peaks-per-day mode DOES commit when the tariff was active.
3. Single-peak-per-day mode already only records peaks during active/reduced
   state (regression guard).
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import (
    ACTIVE_STATE_ON,
    ACTIVE_STATE_OFF,
    ACTIVE_STATE_REDUCED,
)

TZ = ZoneInfo("Europe/Stockholm")


def _make_coordinator(only_one_peak_per_day: bool = False) -> PeakMonitorCoordinator:
    """Build a coordinator with minimal config for peak-commit tests."""
    mock_entry = Mock()
    mock_entry.entry_id = "test_inactive_peaks"
    mock_entry.data = {
        "consumption_sensor": "sensor.energy",
        "sensor_resets_every_hour": True,
        "only_one_peak_per_day": only_one_peak_per_day,
        "number_of_peaks": 3,
        "reset_value": 500,
        "active_start_hour": 6,
        "active_end_hour": 22,
        "active_months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "weekend_behavior": "no_tariff",
        "holiday_behavior": "no_tariff",
        "holidays": [],
        "daily_reduced_tariff_enabled": False,
        "reduced_start_hour": 22,
        "reduced_end_hour": 6,
        "reduced_factor": 0.5,
        "reduced_also_on_weekends": False,
    }
    mock_entry.options = {}

    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states = Mock()
    mock_hass.states.get = Mock(return_value=None)

    coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
    coordinator._async_save_data = AsyncMock()
    coordinator._async_notify_listeners = AsyncMock()
    coordinator._schedule_next_daily_reset = Mock()
    coordinator._schedule_next_hourly_update = Mock()
    return coordinator


class TestMultiplePeaksModeInactiveHours:
    """Multiple-peaks mode: inactive hours must not commit peaks."""

    def test_inactive_hour_not_committed(self):
        """An hour ending while tariff is inactive must be skipped."""
        coord = _make_coordinator(only_one_peak_per_day=False)
        # Simulate that a lot of consumption happened this hour
        coord.hour_cumulative_consumption = 8000.0
        initial_peaks = list(coord.monthly_peaks)

        # The hourly callback fires at 05:00 — the ending hour (04:xx) is inactive
        inactive_now = datetime(2024, 1, 15, 5, 0, 0, tzinfo=TZ)  # 05:00

        # Verify tariff is truly inactive one minute before (04:59)
        state_at_ending_hour = coord.get_tariff_active_state(inactive_now - timedelta(minutes=1))
        assert state_at_ending_hour == ACTIVE_STATE_OFF, (
            f"Expected tariff inactive at 04:59, got {state_at_ending_hour}"
        )

        asyncio.run(coord._async_update_hourly(inactive_now))

        # Monthly peaks must be unchanged — inactive hour was NOT committed
        assert coord.monthly_peaks == initial_peaks, (
            f"Inactive hour was incorrectly committed. "
            f"Peaks changed from {initial_peaks} to {coord.monthly_peaks}"
        )

    def test_active_hour_is_committed(self):
        """An hour ending while tariff is active must be committed if large enough."""
        coord = _make_coordinator(only_one_peak_per_day=False)
        # Start with low peaks so a new high value will qualify
        coord.monthly_peaks = [500, 500, 500]
        coord.hour_cumulative_consumption = 3000.0

        # The hourly callback fires at 14:00 — the ending hour (13:xx) is active
        active_now = datetime(2024, 1, 15, 14, 0, 0, tzinfo=TZ)

        state_at_ending_hour = coord.get_tariff_active_state(active_now - timedelta(minutes=1))
        assert state_at_ending_hour == ACTIVE_STATE_ON, (
            f"Expected tariff active at 13:59, got {state_at_ending_hour}"
        )

        asyncio.run(coord._async_update_hourly(active_now))

        # 3000 Wh should have replaced one of the 500 Wh baseline peaks
        assert 3000.0 in coord.monthly_peaks, (
            f"Active-hour consumption was not committed. Peaks: {coord.monthly_peaks}"
        )

    def test_reduced_hour_is_committed_with_factor(self):
        """An hour ending in reduced state must be committed with the reduction factor applied."""
        mock_entry = Mock()
        mock_entry.entry_id = "test_reduced"
        mock_entry.data = {
            "consumption_sensor": "sensor.energy",
            "sensor_resets_every_hour": True,
            "only_one_peak_per_day": False,
            "number_of_peaks": 3,
            "reset_value": 500,
            "active_start_hour": 6,
            "active_end_hour": 22,
            "active_months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            "weekend_behavior": "no_tariff",
            "holiday_behavior": "no_tariff",
            "holidays": [],
            "daily_reduced_tariff_enabled": True,
            "reduced_start_hour": 22,
            "reduced_end_hour": 6,
            "reduced_factor": 0.5,
            "reduced_also_on_weekends": False,
        }
        mock_entry.options = {}
        mock_hass = Mock()
        mock_hass.data = {}
        mock_hass.states = Mock()
        mock_hass.states.get = Mock(return_value=None)

        coord = PeakMonitorCoordinator(mock_hass, mock_entry)
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord._schedule_next_daily_reset = Mock()
        coord._schedule_next_hourly_update = Mock()

        coord.monthly_peaks = [500, 500, 500]
        coord.hour_cumulative_consumption = 2000.0

        # Hourly callback fires at 23:00 — ending hour (22:xx) is in reduced window
        reduced_now = datetime(2024, 1, 15, 23, 0, 0, tzinfo=TZ)

        state_at_ending_hour = coord.get_tariff_active_state(reduced_now - timedelta(minutes=1))
        assert state_at_ending_hour == ACTIVE_STATE_REDUCED, (
            f"Expected tariff reduced at 22:59, got {state_at_ending_hour}"
        )

        asyncio.run(coord._async_update_hourly(reduced_now))

        # 2000 Wh * 0.5 factor = 1000 Wh should be committed
        assert 1000.0 in coord.monthly_peaks, (
            f"Reduced-hour consumption was not correctly committed with factor. "
            f"Expected 1000.0 in {coord.monthly_peaks}"
        )


class TestSinglePeakModeInactiveGuard:
    """Single-peak mode: inactive peaks must never reach daily_peak (regression guard)."""

    def test_inactive_state_does_not_update_daily_peak(self):
        """Consumption during inactive hours must not update the daily peak."""
        coord = _make_coordinator(only_one_peak_per_day=True)
        initial_daily_peak = coord.daily_peak

        # Simulate an event at 04:30 (inactive) with very high consumption
        inactive_event_time = datetime(2024, 1, 15, 4, 30, 0, tzinfo=TZ)

        # Build a fake state change event
        mock_event = Mock()
        mock_old = Mock()
        mock_old.state = "100"
        mock_new = Mock()
        mock_new.state = "9000"  # 9000 Wh — would be a massive peak

        mock_event.data = {
            "old_state": mock_old,
            "new_state": mock_new,
        }

        with patch("custom_components.peak_monitor.dt_util") as mock_dt:
            mock_dt.now.return_value = inactive_event_time
            asyncio.run(coord._async_consumption_changed(mock_event))

        assert coord.daily_peak == initial_daily_peak, (
            f"Daily peak was updated during inactive period. "
            f"Was {initial_daily_peak}, now {coord.daily_peak}"
        )

    def test_active_state_does_update_daily_peak(self):
        """Consumption during active hours must update the daily peak when it exceeds it."""
        coord = _make_coordinator(only_one_peak_per_day=True)
        coord.daily_peak = 500.0  # Low baseline

        mock_event = Mock()
        mock_old = Mock()
        mock_old.state = "100"
        mock_new = Mock()
        mock_new.state = "2600"  # 2500 Wh difference = above baseline

        mock_event.data = {
            "old_state": mock_old,
            "new_state": mock_new,
        }

        # 14:30 — solidly in the active window
        active_time = datetime(2024, 1, 15, 14, 30, 0, tzinfo=TZ)

        with patch("custom_components.peak_monitor.dt_util") as mock_dt:
            mock_dt.now.return_value = active_time
            asyncio.run(coord._async_consumption_changed(mock_event))

        assert coord.daily_peak > 500.0, (
            f"Daily peak was not updated during active period. Still at {coord.daily_peak}"
        )
