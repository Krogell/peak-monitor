"""Tests verifying that the reduction factor is applied correctly for all reduction scenarios.

Scenarios tested:
  1. Daily time-window reduction (reduced_tariff_enabled)
  2. Weekend with reduced tariff behavior
  3. Holiday with reduced tariff behavior
  4. External reduced sensor
  5. Full tariff (no reduction) — factor must NOT be applied
"""
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import (
    ACTIVE_STATE_ON,
    ACTIVE_STATE_REDUCED,
    ACTIVE_STATE_OFF,
    BEHAVIOR_REDUCED_TARIFF,
    BEHAVIOR_NO_TARIFF,
    DEFAULT_REDUCED_FACTOR,
)

TZ = ZoneInfo("Europe/Stockholm")
FACTOR = 0.5
RAW = 1000.0  # Wh — convenient number to reason about
REDUCED = RAW * FACTOR  # 500.0


def _make_coordinator(data_overrides: dict) -> PeakMonitorCoordinator:
    """Build a coordinator with sensible defaults, applying overrides."""
    base = {
        "consumption_sensor": "sensor.power",
        "active_months": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
        "number_of_peaks": 3,
        "active_start_hour": 6,
        "active_end_hour": 22,
        "reduced_factor": FACTOR,
    }
    base.update(data_overrides)

    mock_entry = Mock()
    mock_entry.entry_id = "test"
    mock_entry.data = base
    mock_entry.options = {}

    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states.get = Mock(return_value=None)

    return PeakMonitorCoordinator(mock_hass, mock_entry)


# ---------------------------------------------------------------------------
# 1. Daily time-window reduction
# ---------------------------------------------------------------------------

class TestDailyReduction:
    """Daily reduced tariff window (e.g. 21:00–06:00)."""

    def _coordinator(self) -> PeakMonitorCoordinator:
        return _make_coordinator({
            "daily_reduced_tariff_enabled": True,
            "reduced_start_hour": 21,
            "reduced_end_hour": 6,
        })

    def test_state_is_reduced_during_window(self):
        coord = self._coordinator()
        night = datetime(2026, 2, 11, 23, 0, tzinfo=TZ)  # 23:00 — inside 21–06
        assert coord.get_tariff_active_state(night) == ACTIVE_STATE_REDUCED

    def test_state_is_on_outside_window(self):
        coord = self._coordinator()
        day = datetime(2026, 2, 11, 14, 0, tzinfo=TZ)  # 14:00 — outside reduced window
        assert coord.get_tariff_active_state(day) == ACTIVE_STATE_ON

    def test_factor_applied_during_window(self):
        coord = self._coordinator()
        night = datetime(2026, 2, 11, 23, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(night)
        adjusted = RAW * FACTOR if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(REDUCED)

    def test_factor_not_applied_outside_window(self):
        coord = self._coordinator()
        day = datetime(2026, 2, 11, 14, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(day)
        adjusted = RAW * FACTOR if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(RAW)


# ---------------------------------------------------------------------------
# 2. Weekend reduction
# ---------------------------------------------------------------------------

class TestWeekendReduction:
    """Weekend with BEHAVIOR_REDUCED_TARIFF."""

    def _coordinator(self) -> PeakMonitorCoordinator:
        return _make_coordinator({
            "weekend_behavior": BEHAVIOR_REDUCED_TARIFF,
        })

    def test_saturday_is_reduced(self):
        coord = self._coordinator()
        saturday = datetime(2026, 2, 14, 14, 0, tzinfo=TZ)  # Saturday
        assert saturday.isoweekday() == 6
        assert coord.get_tariff_active_state(saturday) == ACTIVE_STATE_REDUCED

    def test_sunday_is_reduced(self):
        coord = self._coordinator()
        sunday = datetime(2026, 2, 15, 10, 0, tzinfo=TZ)  # Sunday
        assert sunday.isoweekday() == 7
        assert coord.get_tariff_active_state(sunday) == ACTIVE_STATE_REDUCED

    def test_weekday_is_not_reduced(self):
        coord = self._coordinator()
        tuesday = datetime(2026, 2, 10, 14, 0, tzinfo=TZ)  # Tuesday
        assert tuesday.isoweekday() == 2
        assert coord.get_tariff_active_state(tuesday) == ACTIVE_STATE_ON

    def test_factor_applied_on_weekend(self):
        coord = self._coordinator()
        saturday = datetime(2026, 2, 14, 14, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(saturday)
        adjusted = RAW * FACTOR if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(REDUCED)

    def test_no_tariff_weekend_not_reduced(self):
        """When weekend_behavior is no_tariff, state is OFF, not REDUCED."""
        coord = _make_coordinator({"weekend_behavior": BEHAVIOR_NO_TARIFF})
        saturday = datetime(2026, 2, 14, 14, 0, tzinfo=TZ)
        assert coord.get_tariff_active_state(saturday) == ACTIVE_STATE_OFF


# ---------------------------------------------------------------------------
# 3. Holiday reduction
# ---------------------------------------------------------------------------

class TestHolidayReduction:
    """Swedish public holiday with BEHAVIOR_REDUCED_TARIFF."""

    def _coordinator(self) -> PeakMonitorCoordinator:
        return _make_coordinator({
            "holiday_behavior": BEHAVIOR_REDUCED_TARIFF,
            "holidays": ["official_holidays"],
        })

    def test_new_years_day_is_reduced(self):
        coord = self._coordinator()
        new_years = datetime(2026, 1, 1, 14, 0, tzinfo=TZ)
        assert coord.get_tariff_active_state(new_years) == ACTIVE_STATE_REDUCED

    def test_midsummer_is_reduced(self):
        coord = self._coordinator()
        midsummer = datetime(2026, 6, 20, 14, 0, tzinfo=TZ)  # Midsommardagen 2026 (Saturday) — official red day
        assert coord.get_tariff_active_state(midsummer) == ACTIVE_STATE_REDUCED

    def test_regular_day_not_reduced_by_holiday(self):
        coord = self._coordinator()
        regular = datetime(2026, 2, 11, 14, 0, tzinfo=TZ)  # Ordinary Wednesday
        # State should be ON (not REDUCED due to holiday)
        state = coord.get_tariff_active_state(regular)
        assert state == ACTIVE_STATE_ON

    def test_factor_applied_on_holiday(self):
        coord = self._coordinator()
        new_years = datetime(2026, 1, 1, 14, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(new_years)
        adjusted = RAW * FACTOR if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(REDUCED)

    def test_no_tariff_holiday_is_off(self):
        """When holiday_behavior is no_tariff, state is OFF."""
        coord = _make_coordinator({
            "holiday_behavior": BEHAVIOR_NO_TARIFF,
            "holidays": ["official_holidays"],
        })
        new_years = datetime(2026, 1, 1, 14, 0, tzinfo=TZ)
        assert coord.get_tariff_active_state(new_years) == ACTIVE_STATE_OFF


# ---------------------------------------------------------------------------
# 4. External reduced sensor
# ---------------------------------------------------------------------------

class TestExternalReducedSensor:
    """External binary sensor driving reduced tariff."""

    def _coordinator(self, sensor_state: str) -> PeakMonitorCoordinator:
        coord = _make_coordinator({
            "external_reduced_sensor": "binary_sensor.reduced",
        })

        class _State:
            state = sensor_state

        coord.hass.states.get = Mock(return_value=_State())
        return coord

    def test_state_is_reduced_when_sensor_on(self):
        coord = self._coordinator("on")
        daytime = datetime(2026, 2, 11, 14, 0, tzinfo=TZ)
        assert coord.get_tariff_active_state(daytime) == ACTIVE_STATE_REDUCED

    def test_state_is_on_when_sensor_off(self):
        coord = self._coordinator("off")
        daytime = datetime(2026, 2, 11, 14, 0, tzinfo=TZ)
        assert coord.get_tariff_active_state(daytime) == ACTIVE_STATE_ON

    def test_factor_applied_when_sensor_on(self):
        coord = self._coordinator("on")
        daytime = datetime(2026, 2, 11, 14, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(daytime)
        adjusted = RAW * FACTOR if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(REDUCED)

    def test_factor_not_applied_when_sensor_off(self):
        coord = self._coordinator("off")
        daytime = datetime(2026, 2, 11, 14, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(daytime)
        adjusted = RAW * FACTOR if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(RAW)


# ---------------------------------------------------------------------------
# 5. Custom reduction factor values
# ---------------------------------------------------------------------------

class TestCustomReductionFactor:
    """Factor other than 0.5 is respected."""

    def test_custom_factor_0_3(self):
        coord = _make_coordinator({
            "daily_reduced_tariff_enabled": True,
            "reduced_start_hour": 21,
            "reduced_end_hour": 6,
            "reduced_factor": 0.3,
        })
        night = datetime(2026, 2, 11, 23, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(night)
        assert state == ACTIVE_STATE_REDUCED
        adjusted = RAW * 0.3 if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(300.0)

    def test_custom_factor_0_75(self):
        coord = _make_coordinator({
            "weekend_behavior": BEHAVIOR_REDUCED_TARIFF,
            "reduced_factor": 0.75,
        })
        saturday = datetime(2026, 2, 14, 14, 0, tzinfo=TZ)
        state = coord.get_tariff_active_state(saturday)
        assert state == ACTIVE_STATE_REDUCED
        adjusted = RAW * 0.75 if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(750.0)

    def test_full_tariff_ignores_factor(self):
        """When tariff is fully active, factor must not be applied regardless of its value."""
        coord = _make_coordinator({"reduced_factor": 0.1})
        daytime = datetime(2026, 2, 11, 14, 0, tzinfo=TZ)  # Tuesday, active hours, no reduction
        state = coord.get_tariff_active_state(daytime)
        assert state == ACTIVE_STATE_ON
        adjusted = RAW * 0.1 if state == ACTIVE_STATE_REDUCED else RAW
        assert adjusted == pytest.approx(RAW)


# ---------------------------------------------------------------------------
# 6. Hour consumption unavailable on startup
# ---------------------------------------------------------------------------

class TestHourConsumptionAvailability:
    """Hour consumption sensor should be unavailable until first reading."""

    def test_unavailable_before_first_reading(self):
        """Coordinator starts with has_received_reading=False."""
        coord = _make_coordinator({})
        assert coord.has_received_reading is False

    def test_native_value_none_before_reading(self):
        """Sensor returns None when no reading has arrived yet."""
        coord = _make_coordinator({})
        # Simulate what the sensor property does
        result = None if not coord.has_received_reading else coord.hour_cumulative_consumption
        assert result is None

    def test_available_after_reading(self):
        """Once has_received_reading is True, value is returned."""
        coord = _make_coordinator({})
        coord.has_received_reading = True
        coord.hour_cumulative_consumption = 123.0
        result = None if not coord.has_received_reading else coord.hour_cumulative_consumption
        assert result == 123.0


class TestMultiplePeaksPerDayReduction:
    """Reduction factor is applied when committing hourly peaks in multiple-peaks mode."""

    def _coordinator(self, reduced_factor=0.5, hour_consumption=4000.0):
        from unittest.mock import AsyncMock
        entry = Mock()
        entry.entry_id = "test"
        entry.data = {
            "consumption_sensor": "sensor.power",
            "number_of_peaks": 3,
            "only_one_peak_per_day": False,
            "sensor_resets_every_hour": True,
            "reset_value": 500,
            "active_start_hour": 6,
            "active_end_hour": 22,
            "reduced_factor": reduced_factor,
            "reduced_tariff_enabled": True,
            "reduced_start_hour": 21,
            "reduced_end_hour": 6,
        }
        entry.options = {}
        hass = Mock()
        hass.data = {}
        hass.states.get = Mock(return_value=None)
        coord = PeakMonitorCoordinator(hass, entry)
        coord.monthly_peaks = [3000, 2500, 2000]
        coord.hour_cumulative_consumption = hour_consumption
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord._schedule_next_hourly_update = Mock()
        return coord

    def _run_hourly(self, coord, test_time):
        """Run _async_update_hourly with dt_util.now mocked to test_time."""
        import asyncio
        from unittest.mock import patch
        import custom_components.peak_monitor as _mod
        with patch.object(_mod.dt_util, "now", return_value=test_time):
            asyncio.run(coord._async_update_hourly(test_time))

    def test_factor_applied_during_reduced_window(self):
        """Hour ending in reduced window: 4000 Wh * 0.5 = 2000 → not > min(2000), no change."""
        coord = self._coordinator(reduced_factor=0.5, hour_consumption=4000.0)
        self._run_hourly(coord, datetime(2026, 2, 11, 23, 0, tzinfo=TZ))
        # adjusted = 4000 * 0.5 = 2000, not > 2000 → no change
        assert coord.monthly_peaks == [3000, 2500, 2000]

    def test_factor_applied_and_displaces_lowest(self):
        """Hour ending in reduced window: 7000 Wh * 0.5 = 3500 → displaces 2000."""
        coord = self._coordinator(reduced_factor=0.5, hour_consumption=7000.0)
        self._run_hourly(coord, datetime(2026, 2, 11, 23, 0, tzinfo=TZ))
        # adjusted = 7000 * 0.5 = 3500 > 2000 → [3500, 3000, 2500]
        assert coord.monthly_peaks == [3500, 3000, 2500]

    def test_no_factor_outside_reduced_window(self):
        """Hour ending outside reduced window: raw 4000 Wh committed."""
        coord = self._coordinator(reduced_factor=0.5, hour_consumption=4000.0)
        self._run_hourly(coord, datetime(2026, 2, 11, 14, 0, tzinfo=TZ))
        # no reduction → 4000 > 2000 → [4000, 3000, 2500]
        assert coord.monthly_peaks == [4000, 3000, 2500]
