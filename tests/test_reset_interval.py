"""Test configurable reset interval (weekly, monthly, manual)."""
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock
from zoneinfo import ZoneInfo

import pytest

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import (
    ACTIVE_STATE_ON,
    RESET_INTERVAL_WEEKLY,
    RESET_INTERVAL_MONTHLY,
    RESET_INTERVAL_MANUAL,
)

TZ = ZoneInfo("Europe/Stockholm")


def make_coordinator(reset_interval: str, peaks=None) -> PeakMonitorCoordinator:
    mock_entry = Mock()
    mock_entry.entry_id = "test"
    mock_entry.data = {
        "consumption_sensor": "sensor.power",
        "reset_interval": reset_interval,
    }
    mock_entry.options = {}
    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states.get = Mock(return_value=None)
    coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
    coordinator._async_save_data = AsyncMock()
    coordinator._async_notify_listeners = AsyncMock()
    coordinator._schedule_next_daily_reset = Mock()
    if peaks:
        coordinator.monthly_peaks = peaks
    return coordinator


class TestResetIntervalMonthly:
    """Monthly reset is the default behaviour."""

    def test_monthly_reset_triggers_on_month_change(self):
        coordinator = make_coordinator(RESET_INTERVAL_MONTHLY)
        coordinator.monthly_peaks = [1200, 1100, 1000]
        coordinator.daily_peak = 800
        coordinator.last_month = 2  # February

        now = datetime(2025, 3, 1, 0, 0, 5, tzinfo=TZ)
        asyncio.run(coordinator._async_update_daily(now))

        assert all(p == coordinator.reset_value for p in coordinator.monthly_peaks)

    def test_monthly_reset_does_not_trigger_mid_month(self):
        coordinator = make_coordinator(RESET_INTERVAL_MONTHLY)
        coordinator.monthly_peaks = [1200, 1100, 1000]
        coordinator.daily_peak = 800
        coordinator.last_month = 3  # Same month

        now = datetime(2025, 3, 15, 0, 0, 5, tzinfo=TZ)
        asyncio.run(coordinator._async_update_daily(now))

        assert coordinator.monthly_peaks[0] >= 1000


class TestResetIntervalWeekly:
    """Weekly reset: peaks reset on Monday midnight."""

    def test_weekly_reset_triggers_on_monday(self):
        coordinator = make_coordinator(RESET_INTERVAL_WEEKLY)
        coordinator.monthly_peaks = [1200, 1100, 1000]
        coordinator.daily_peak = 800
        coordinator.last_month = 3

        now = datetime(2025, 3, 3, 0, 0, 5, tzinfo=TZ)  # Monday
        assert now.isoweekday() == 1
        asyncio.run(coordinator._async_update_daily(now))

        assert all(p == coordinator.reset_value for p in coordinator.monthly_peaks)

    def test_weekly_reset_does_not_trigger_on_non_monday(self):
        coordinator = make_coordinator(RESET_INTERVAL_WEEKLY)
        coordinator.monthly_peaks = [1200, 1100, 1000]
        coordinator.daily_peak = 800
        coordinator.last_month = 3

        now = datetime(2025, 3, 5, 0, 0, 5, tzinfo=TZ)  # Wednesday
        assert now.isoweekday() == 3
        asyncio.run(coordinator._async_update_daily(now))

        assert coordinator.monthly_peaks[0] >= 1000


class TestResetIntervalManual:
    """Manual only: peaks are never automatically reset."""

    def test_manual_peaks_not_reset_on_month_change(self):
        coordinator = make_coordinator(RESET_INTERVAL_MANUAL)
        coordinator.monthly_peaks = [1200, 1100, 1000]
        coordinator.daily_peak = 800
        coordinator.last_month = 2

        now = datetime(2025, 3, 1, 0, 0, 5, tzinfo=TZ)
        asyncio.run(coordinator._async_update_daily(now))

        assert coordinator.monthly_peaks[0] >= 1000

    def test_manual_daily_peak_still_reset(self):
        """Daily peak (current-hour tracker) should still reset each day."""
        coordinator = make_coordinator(RESET_INTERVAL_MANUAL)
        coordinator.monthly_peaks = [1200, 1100, 1000]
        coordinator.daily_peak = 1500
        coordinator.last_month = 3

        now = datetime(2025, 3, 15, 0, 0, 5, tzinfo=TZ)
        asyncio.run(coordinator._async_update_daily(now))

        assert coordinator.daily_peak == coordinator.reset_value
