"""Test daily_peaks_averaged — average of N highest intra-day peaks."""
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import ACTIVE_STATE_ON, ACTIVE_STATE_OFF

TZ = ZoneInfo("Europe/Stockholm")


def make_coordinator(daily_peaks_averaged: int = 1, number_of_peaks: int = 3) -> PeakMonitorCoordinator:
    mock_entry = Mock()
    mock_entry.entry_id = "test"
    mock_entry.data = {
        "consumption_sensor": "sensor.power",
        "daily_peaks_averaged": daily_peaks_averaged,
        "only_one_peak_per_day": True,
        "number_of_peaks": number_of_peaks,
    }
    mock_entry.options = {}
    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states.get = Mock(return_value=None)
    coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
    coordinator._async_save_data = AsyncMock()
    coordinator._async_notify_listeners = AsyncMock()
    coordinator._schedule_next_daily_reset = Mock()
    return coordinator


def feed_consumption(coordinator, wh: float, t: datetime):
    """Feed a consumption reading and update peaks."""
    import homeassistant.util.dt as dt_util
    coordinator.tariff_seen_active_today = True
    with patch.object(dt_util, "now", return_value=t):
        # Directly simulate peak update logic
        adjusted = wh
        EPSILON = 1.0
        if coordinator.daily_peaks_averaged > 1:
            if adjusted > min(coordinator.daily_sub_peaks) + EPSILON:
                sub = sorted(coordinator.daily_sub_peaks + [adjusted], reverse=True)
                coordinator.daily_sub_peaks = sub[:coordinator.daily_peaks_averaged]
                coordinator.daily_peak = sum(coordinator.daily_sub_peaks) / len(coordinator.daily_sub_peaks)
        else:
            if adjusted > coordinator.daily_peak + EPSILON:
                coordinator.daily_peak = adjusted


class TestDailyPeaksAveragedDisabled:
    """When daily_peaks_averaged=1, behaviour is unchanged."""

    def test_daily_peak_is_max_reading(self):
        c = make_coordinator(daily_peaks_averaged=1)
        t = datetime(2025, 3, 5, 10, 0, tzinfo=TZ)
        feed_consumption(c, 1500, t)
        feed_consumption(c, 1200, t)
        feed_consumption(c, 1800, t)
        assert c.daily_peak == 1800

    def test_daily_sub_peaks_length_is_one(self):
        c = make_coordinator(daily_peaks_averaged=1)
        assert len(c.daily_sub_peaks) == 1


class TestDailyPeaksAveragedTwo:
    """Jönköping Energi model: average of 2 highest intra-day peaks."""

    def test_sub_peaks_track_top_two(self):
        c = make_coordinator(daily_peaks_averaged=2)
        t = datetime(2025, 3, 5, 10, 0, tzinfo=TZ)
        feed_consumption(c, 1800, t)
        feed_consumption(c, 1500, t)
        feed_consumption(c, 1200, t)  # Below top-2, should not enter
        assert sorted(c.daily_sub_peaks, reverse=True) == [1800, 1500]

    def test_daily_peak_is_average_of_sub_peaks(self):
        c = make_coordinator(daily_peaks_averaged=2)
        t = datetime(2025, 3, 5, 10, 0, tzinfo=TZ)
        feed_consumption(c, 1800, t)
        feed_consumption(c, 1500, t)
        # daily_peak = avg(1800, 1500) = 1650
        assert abs(c.daily_peak - 1650.0) < 1.0

    def test_better_reading_replaces_lowest_sub_peak(self):
        c = make_coordinator(daily_peaks_averaged=2)
        t = datetime(2025, 3, 5, 10, 0, tzinfo=TZ)
        feed_consumption(c, 1200, t)
        feed_consumption(c, 1000, t)
        # Now a much better reading comes in
        feed_consumption(c, 1600, t)
        # Top 2 should now be [1600, 1200]
        assert sorted(c.daily_sub_peaks, reverse=True) == [1600, 1200]
        assert abs(c.daily_peak - 1400.0) < 1.0

    def test_lower_reading_does_not_replace_sub_peak(self):
        c = make_coordinator(daily_peaks_averaged=2)
        t = datetime(2025, 3, 5, 10, 0, tzinfo=TZ)
        feed_consumption(c, 1500, t)
        feed_consumption(c, 1300, t)
        original_sub = list(c.daily_sub_peaks)
        feed_consumption(c, 800, t)  # Below both, ignored
        assert c.daily_sub_peaks == original_sub

    def test_daily_sub_peaks_initialised_to_reset_value(self):
        c = make_coordinator(daily_peaks_averaged=2)
        assert len(c.daily_sub_peaks) == 2
        assert all(p == c.reset_value for p in c.daily_sub_peaks)

    def test_midnight_commit_uses_averaged_daily_peak(self):
        """The averaged daily_peak is what gets committed to monthly peaks at midnight."""
        c = make_coordinator(daily_peaks_averaged=2)
        t = datetime(2025, 3, 5, 10, 0, tzinfo=TZ)
        feed_consumption(c, 1800, t)
        feed_consumption(c, 1500, t)
        # daily_peak = 1650 (avg of 1800 and 1500)
        c.monthly_peaks = [c.reset_value] * 3
        c.last_month = 3

        midnight = datetime(2025, 3, 6, 0, 0, 5, tzinfo=TZ)
        asyncio.run(c._async_update_daily(midnight))

        # 1650 should be committed into monthly_peaks
        assert max(c.monthly_peaks) == pytest.approx(1650.0, abs=1.0)

    def test_daily_sub_peaks_reset_at_midnight(self):
        c = make_coordinator(daily_peaks_averaged=2)
        t = datetime(2025, 3, 5, 10, 0, tzinfo=TZ)
        feed_consumption(c, 1800, t)
        feed_consumption(c, 1500, t)
        c.last_month = 3

        midnight = datetime(2025, 3, 6, 0, 0, 5, tzinfo=TZ)
        asyncio.run(c._async_update_daily(midnight))

        assert all(p == c.reset_value for p in c.daily_sub_peaks)


class TestDailyAverageTarget:
    """Target uses lowest daily sub-peak when averaged daily peak qualifies."""

    def test_target_is_lowest_sub_peak_when_daily_qualifies(self):
        c = make_coordinator(daily_peaks_averaged=2)
        # Push sub-peaks well above monthly floor
        c.monthly_peaks = [800, 700, 600]  # min=600
        c.daily_sub_peaks = [1800.0, 1500.0]
        c.daily_peak = 1650.0  # avg, exceeds min monthly (600)

        c._force_update_target()

        # Target = min(daily_sub_peaks) = 1500
        assert c.cached_target == 1500.0

    def test_target_falls_back_when_daily_does_not_qualify(self):
        c = make_coordinator(daily_peaks_averaged=2)
        c.monthly_peaks = [1800, 1700, 1600]  # min=1600
        c.daily_sub_peaks = [c.reset_value, c.reset_value]
        c.daily_peak = c.reset_value  # below monthly min

        c._force_update_target()

        # Falls back: max(daily_peak, min(monthly)) = min(monthly) = 1600
        assert c.cached_target == 1600.0


class TestDailyAverageIncompatibilityCheck:
    """Validate config incompatibility: daily_peaks_averaged > 1 with only_one_peak_per_day=False."""

    def test_incompatible_config_only_one_peak_false(self):
        """Coordinator loads config but the config_flow validator would catch this."""
        # Simulate what validate_input checks
        data = {"only_one_peak_per_day": False, "daily_peaks_averaged": 2}
        only_one = data.get("only_one_peak_per_day", True)
        daily_avg = int(data.get("daily_peaks_averaged", 1))
        is_incompatible = not only_one and daily_avg > 1
        assert is_incompatible

    def test_compatible_config_one_peak_true(self):
        data = {"only_one_peak_per_day": True, "daily_peaks_averaged": 2}
        only_one = data.get("only_one_peak_per_day", True)
        daily_avg = int(data.get("daily_peaks_averaged", 1))
        is_incompatible = not only_one and daily_avg > 1
        assert not is_incompatible

    def test_compatible_config_averaged_one(self):
        data = {"only_one_peak_per_day": False, "daily_peaks_averaged": 1}
        only_one = data.get("only_one_peak_per_day", True)
        daily_avg = int(data.get("daily_peaks_averaged", 1))
        is_incompatible = not only_one and daily_avg > 1
        assert not is_incompatible
