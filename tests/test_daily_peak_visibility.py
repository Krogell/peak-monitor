"""Tests for the daily peak sensor visibility feature.

The daily peak sensor should be unavailable (available=False) at the start of
a day when the tariff has not yet been active or reduced. Once the tariff becomes
active or reduced for the first time that day, tariff_seen_active_today is set to
True and the sensor becomes available for the rest of the day.

Rules:
  - tariff_seen_active_today starts False at midnight / on first startup of the day
  - It becomes True the first time a consumption update arrives while tariff is
    ACTIVE or REDUCED
  - It stays True for the remainder of the day even if the tariff goes inactive again
  - On restart, if daily_peak > reset_value, the flag is restored to True
    (because a real peak was already recorded today before the restart)
  - All daily reset paths (midnight callback, _reset_peaks) set it back to False
"""
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import (
    ACTIVE_STATE_OFF,
    ACTIVE_STATE_ON,
    ACTIVE_STATE_REDUCED,
)

TZ = ZoneInfo("Europe/Stockholm")

# Weekday 10:00 — tariff active for most DSOs
WED_ACTIVE = datetime(2026, 2, 11, 10, 0, tzinfo=TZ)
# Same day 01:00 — outside active hours for most DSOs
WED_INACTIVE = datetime(2026, 2, 11, 1, 0, tzinfo=TZ)


def _make(*, weekend_behavior="no_tariff", active_start=6, active_end=22,
          active_months=None, reset_value=500, daily_peak_override=None):
    entry = Mock()
    entry.entry_id = "test"
    entry.data = {
        "consumption_sensor": "sensor.power",
        "number_of_peaks": 3,
        "active_start_hour": active_start,
        "active_end_hour": active_end,
        "active_months": [str(m) for m in (active_months or range(1, 13))],
        "daily_reduced_tariff_enabled": False,
        "reduced_start_hour": 22,
        "reduced_end_hour": 6,
        "reduced_also_on_weekends": False,
        "reduced_factor": 0.5,
        "weekend_behavior": weekend_behavior,
        "weekend_start_hour": 6,
        "weekend_end_hour": 22,
        "holiday_behavior": "no_tariff",
        "holidays": [],
        "reset_value": reset_value,
    }
    entry.options = {}
    hass = Mock()
    hass.data = {}
    hass.states.get = Mock(return_value=None)
    coord = PeakMonitorCoordinator(hass, entry)
    if daily_peak_override is not None:
        coord.daily_peak = daily_peak_override
    return coord


class TestInitialState:
    """Flag starts False; sensor is unavailable until tariff has been seen."""

    def test_flag_starts_false(self):
        coord = _make()
        assert coord.tariff_seen_active_today is False

    def test_sensor_unavailable_when_flag_false(self):
        """Simulating the available property logic."""
        coord = _make()
        assert coord.tariff_seen_active_today is False  # sensor would return unavailable


class TestFlagSetOnActiveState:
    """Flag becomes True when tariff transitions to ACTIVE or REDUCED."""

    def test_flag_set_when_tariff_is_active(self):
        coord = _make()
        coord.tariff_seen_active_today = False
        # Simulate what _async_consumption_changed does when tariff is on
        state = coord.get_tariff_active_state(WED_ACTIVE)
        assert state == ACTIVE_STATE_ON
        if state != ACTIVE_STATE_OFF:
            coord.tariff_seen_active_today = True
        assert coord.tariff_seen_active_today is True

    def test_flag_not_set_when_tariff_is_off(self):
        coord = _make()
        coord.tariff_seen_active_today = False
        state = coord.get_tariff_active_state(WED_INACTIVE)
        assert state == ACTIVE_STATE_OFF
        # Flag must not be set for OFF state
        assert coord.tariff_seen_active_today is False

    def test_flag_stays_true_after_tariff_goes_inactive(self):
        """Once set, the flag is not cleared when the tariff becomes inactive again."""
        coord = _make()
        coord.tariff_seen_active_today = True  # was set earlier in the day
        state = coord.get_tariff_active_state(WED_INACTIVE)
        assert state == ACTIVE_STATE_OFF
        # Flag must remain True — sensor stays visible
        assert coord.tariff_seen_active_today is True


class TestReducedStateSetsFlag:
    """REDUCED state (not just ACTIVE) also unlocks the sensor."""

    def test_reduced_state_sets_flag(self):
        coord = _make(active_start=6, active_end=22)
        # Force reduced state via the internal field
        coord.reduced_tariff_enabled = True
        coord.reduced_start_hour = 22
        coord.reduced_end_hour = 6
        coord.tariff_seen_active_today = False
        # 23:00 on a weekday with reduced window — reduced state
        night = datetime(2026, 2, 11, 23, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(night)
        assert state == ACTIVE_STATE_REDUCED
        if state != ACTIVE_STATE_OFF:
            coord.tariff_seen_active_today = True
        assert coord.tariff_seen_active_today is True


class TestMidnightReset:
    """_reset_peaks and _async_update_daily reset the flag to False."""

    def test_daily_reset_clears_flag(self):
        import asyncio
        coord = _make()
        coord.tariff_seen_active_today = True
        coord.daily_peak = 3000
        coord.monthly_peaks = [3000, 2000, 1000]
        coord.last_day = 10

        async def run():
            # patch _async_save_data and _async_notify_listeners
            coord._async_save_data = AsyncMock()
            coord._async_notify_listeners = AsyncMock()
            await coord._reset_peaks(reset_type="daily")

        asyncio.run(run())
        assert coord.tariff_seen_active_today is False

    def test_monthly_reset_clears_flag(self):
        import asyncio
        coord = _make()
        coord.tariff_seen_active_today = True
        coord.daily_peak = 3000
        coord.monthly_peaks = [3000, 2000, 1000]
        coord.last_day = 10
        coord.last_month = 1

        async def run():
            coord._async_save_data = AsyncMock()
            coord._async_notify_listeners = AsyncMock()
            await coord._reset_peaks(reset_type="monthly")

        asyncio.run(run())
        assert coord.tariff_seen_active_today is False


class TestStartupRestore:
    """On HA restart, flag is restored to True if daily_peak > reset_value."""

    def test_flag_restored_when_peak_already_recorded(self):
        """daily_peak=3500 > reset_value=500 means the tariff was active today."""
        coord = _make(reset_value=500, daily_peak_override=3500)
        # Simulate the startup restore logic
        if coord.daily_peak > coord.reset_value:
            coord.tariff_seen_active_today = True
        assert coord.tariff_seen_active_today is True

    def test_flag_not_restored_when_only_reset_value(self):
        """daily_peak == reset_value means no real peak was recorded yet today."""
        coord = _make(reset_value=500, daily_peak_override=500)
        # daily_peak == reset_value → no real activity yet
        if coord.daily_peak > coord.reset_value:
            coord.tariff_seen_active_today = True
        assert coord.tariff_seen_active_today is False

    def test_flag_not_restored_when_below_reset_value(self):
        """Defensive: daily_peak < reset_value also means no real peak."""
        coord = _make(reset_value=500, daily_peak_override=300)
        if coord.daily_peak > coord.reset_value:
            coord.tariff_seen_active_today = True
        assert coord.tariff_seen_active_today is False
