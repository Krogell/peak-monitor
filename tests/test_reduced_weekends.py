"""Tests for the 'reduced_also_on_weekends' setting.

Priority order (highest to lowest):
  1. INACTIVE  — external mute, excluded month, holiday, outside active hours
  2. REDUCED   — reduced_also_on_weekends window, weekend_behavior=reduced, external reduced sensor
  3. ACTIVE    — normal active hours

These tests verify that:
  - Without the flag, the daily reduced window does NOT fire on weekends.
  - With the flag, the daily reduced window fires on weekends, returning REDUCED.
  - INACTIVE is still dominant — even with the flag, an excluded month or external
    mute overrides everything.
  - REDUCED is dominant over ACTIVE — the flag wins over weekend_behavior=full_tariff.
  - Outside the reduced window on weekends, weekend_behavior still applies normally.
"""
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import (
    ACTIVE_STATE_OFF,
    ACTIVE_STATE_ON,
    ACTIVE_STATE_REDUCED,
)

TZ = ZoneInfo("Europe/Stockholm")

# Saturday at 22:30 — inside a typical 21–06 reduced window
SAT_REDUCED = datetime(2026, 2, 7, 22, 30, tzinfo=TZ)   # Saturday 22:30
SAT_ACTIVE  = datetime(2026, 2, 7, 14, 0,  tzinfo=TZ)   # Saturday 14:00
SUN_REDUCED = datetime(2026, 2, 8, 3, 0,   tzinfo=TZ)   # Sunday 03:00
WED_REDUCED = datetime(2026, 2, 11, 22, 30, tzinfo=TZ)  # Wednesday 22:30 (weekday)
WED_ACTIVE  = datetime(2026, 2, 11, 10, 0,  tzinfo=TZ)  # Wednesday 10:00 (weekday)


def _make(
    *,
    reduced_tariff_enabled=True,
    reduced_start_hour=21,
    reduced_end_hour=6,
    reduced_also_on_weekends=False,
    weekend_behavior="no_tariff",
    active_months=None,
    external_mute=False,
):
    entry = Mock()
    entry.entry_id = "test"
    entry.data = {
        "consumption_sensor": "sensor.power",
        "number_of_peaks": 3,
        "active_start_hour": 6,
        "active_end_hour": 22,
        "active_months": [str(m) for m in (active_months or list(range(1, 13)))],
        "daily_reduced_tariff_enabled": reduced_tariff_enabled,
        "reduced_start_hour": reduced_start_hour,
        "reduced_end_hour": reduced_end_hour,
        "reduced_also_on_weekends": reduced_also_on_weekends,
        "reduced_factor": 0.5,
        "weekend_behavior": weekend_behavior,
        "weekend_start_hour": 6,
        "weekend_end_hour": 22,
        "holiday_behavior": "no_tariff",
        "holidays": [],
    }
    entry.options = {}
    hass = Mock()
    hass.data = {}
    if external_mute:
        mute_state = Mock()
        mute_state.state = "on"
        hass.states.get = Mock(return_value=mute_state)
        entry.data["external_mute_sensor"] = "binary_sensor.mute"
    else:
        hass.states.get = Mock(return_value=None)
    coord = PeakMonitorCoordinator(hass, entry)
    return coord


# ---------------------------------------------------------------------------
# Baseline: flag OFF — weekday behaviour unchanged
# ---------------------------------------------------------------------------

class TestFlagOff:
    """Without the flag, weekday reduced windows work as always."""

    def test_weekday_in_reduced_window_returns_reduced(self):
        coord = _make(reduced_also_on_weekends=False)
        assert coord.get_tariff_active_state(WED_REDUCED) == ACTIVE_STATE_REDUCED

    def test_weekday_in_active_hours_returns_on(self):
        coord = _make(reduced_also_on_weekends=False)
        assert coord.get_tariff_active_state(WED_ACTIVE) == ACTIVE_STATE_ON

    def test_saturday_in_reduced_window_is_off_without_flag(self):
        """Weekend_behavior=no_tariff → OFF even during the reduced window."""
        coord = _make(reduced_also_on_weekends=False, weekend_behavior="no_tariff")
        assert coord.get_tariff_active_state(SAT_REDUCED) == ACTIVE_STATE_OFF

    def test_saturday_outside_reduced_window_is_off(self):
        coord = _make(reduced_also_on_weekends=False, weekend_behavior="no_tariff")
        assert coord.get_tariff_active_state(SAT_ACTIVE) == ACTIVE_STATE_OFF


# ---------------------------------------------------------------------------
# Flag ON — reduced window also fires on weekends
# ---------------------------------------------------------------------------

class TestFlagOn:
    """With the flag, the daily reduced window applies on Saturdays and Sundays."""

    def test_saturday_in_reduced_window_returns_reduced(self):
        coord = _make(reduced_also_on_weekends=True, weekend_behavior="no_tariff")
        assert coord.get_tariff_active_state(SAT_REDUCED) == ACTIVE_STATE_REDUCED

    def test_sunday_in_reduced_window_returns_reduced(self):
        coord = _make(reduced_also_on_weekends=True, weekend_behavior="no_tariff")
        assert coord.get_tariff_active_state(SUN_REDUCED) == ACTIVE_STATE_REDUCED

    def test_saturday_outside_reduced_window_still_obeys_weekend_behavior_no_tariff(self):
        """Outside the reduced window, weekend_behavior=no_tariff → OFF."""
        coord = _make(reduced_also_on_weekends=True, weekend_behavior="no_tariff")
        assert coord.get_tariff_active_state(SAT_ACTIVE) == ACTIVE_STATE_OFF

    def test_saturday_outside_reduced_window_full_tariff_returns_on(self):
        """Outside the reduced window, weekend_behavior=full_tariff → ON."""
        coord = _make(reduced_also_on_weekends=True, weekend_behavior="full_tariff")
        assert coord.get_tariff_active_state(SAT_ACTIVE) == ACTIVE_STATE_ON

    def test_saturday_outside_reduced_window_reduced_tariff_returns_reduced(self):
        """Outside the reduced window, weekend_behavior=reduced_tariff → REDUCED."""
        coord = _make(reduced_also_on_weekends=True, weekend_behavior="reduced_tariff")
        assert coord.get_tariff_active_state(SAT_ACTIVE) == ACTIVE_STATE_REDUCED

    def test_weekday_still_reduced_in_window(self):
        """Enabling the flag must not break weekday reduced windows."""
        coord = _make(reduced_also_on_weekends=True)
        assert coord.get_tariff_active_state(WED_REDUCED) == ACTIVE_STATE_REDUCED

    def test_disabled_reduced_tariff_flag_has_no_effect_on_weekends(self):
        """reduced_tariff_enabled=False overrides reduced_also_on_weekends."""
        coord = _make(reduced_tariff_enabled=False, reduced_also_on_weekends=True,
                      weekend_behavior="no_tariff")
        assert coord.get_tariff_active_state(SAT_REDUCED) == ACTIVE_STATE_OFF


# ---------------------------------------------------------------------------
# Priority: INACTIVE dominates everything
# ---------------------------------------------------------------------------

class TestInactiveDominates:
    """INACTIVE state wins even when reduced_also_on_weekends is True."""

    def test_excluded_month_overrides_reduced_weekend(self):
        """Month not in active_months → OFF, even on a reduced weekend."""
        coord = _make(reduced_also_on_weekends=True, active_months=[3, 4, 5])
        # SAT_REDUCED is in February — excluded
        assert coord.get_tariff_active_state(SAT_REDUCED) == ACTIVE_STATE_OFF

    def test_external_mute_overrides_reduced_weekend(self):
        """External mute sensor → OFF, even on a reduced weekend."""
        coord = _make(reduced_also_on_weekends=True, external_mute=True)
        assert coord.get_tariff_active_state(SAT_REDUCED) == ACTIVE_STATE_OFF


# ---------------------------------------------------------------------------
# Ellevio-style configuration
# ---------------------------------------------------------------------------

class TestEllevioConfig:
    """Ellevio: top 3 peaks, one per day, 22–06 reduced (factor 0.5), every day."""

    def _ellevio(self):
        return _make(
            reduced_tariff_enabled=True,
            reduced_start_hour=22,
            reduced_end_hour=6,
            reduced_also_on_weekends=True,
            weekend_behavior="no_tariff",   # weekends outside 22–06 are inactive
        )

    def test_weekday_night_is_reduced(self):
        wed_night = datetime(2026, 2, 11, 23, 0, tzinfo=TZ)
        assert self._ellevio().get_tariff_active_state(wed_night) == ACTIVE_STATE_REDUCED

    def test_saturday_night_is_reduced(self):
        sat_night = datetime(2026, 2, 7, 23, 0, tzinfo=TZ)
        assert self._ellevio().get_tariff_active_state(sat_night) == ACTIVE_STATE_REDUCED

    def test_sunday_early_morning_is_reduced(self):
        sun_am = datetime(2026, 2, 8, 4, 0, tzinfo=TZ)
        assert self._ellevio().get_tariff_active_state(sun_am) == ACTIVE_STATE_REDUCED

    def test_saturday_afternoon_is_off(self):
        """Saturday 14:00 is outside the reduced window and weekend_behavior=no_tariff."""
        sat_pm = datetime(2026, 2, 7, 14, 0, tzinfo=TZ)
        assert self._ellevio().get_tariff_active_state(sat_pm) == ACTIVE_STATE_OFF

    def test_weekday_active_hours_is_on(self):
        wed_day = datetime(2026, 2, 11, 10, 0, tzinfo=TZ)
        assert self._ellevio().get_tariff_active_state(wed_day) == ACTIVE_STATE_ON
