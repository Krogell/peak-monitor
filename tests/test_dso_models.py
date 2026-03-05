"""Unit tests for DSO tariff configurations.

Each class tests a specific DSO's recommended Peak Monitor configuration,
verifying that the state machine returns the correct ACTIVE/REDUCED/OFF
state for representative timestamps.

Sources used (verified Feb 2026):
  - Ellevio:          ellevio.se, byggahus.se, elinstallatoren.se
  - Göteborg Energi:  goteborgenergi.se
  - Vattenfall:       grontsamhallsbyggande.se, byggahus.se
  - Tekniska verken:  byggahus.se, effekttariff.nu
  - Umeå Energi:      byggahus.se

DSO configurations are documented in docs/CONFIGURATION_EXAMPLES.md.
Always verify with your own DSO before relying on these settings.
"""
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import (
    ACTIVE_STATE_OFF,
    ACTIVE_STATE_ON,
    ACTIVE_STATE_REDUCED,
    HOLIDAY_OFFICIAL,
    HOLIDAY_CHRISTMAS_EVE,
    HOLIDAY_NEW_YEARS_EVE,
)

TZ = ZoneInfo("Europe/Stockholm")

# ---------------------------------------------------------------------------
# Calendar fixtures — all in winter (February 2026) so seasonal DSOs are active
# ---------------------------------------------------------------------------

# Week of Mon 2 Feb – Sun 8 Feb 2026
MON = datetime(2026, 2,  2, tzinfo=TZ)
TUE = datetime(2026, 2,  3, tzinfo=TZ)
SAT = datetime(2026, 2,  7, tzinfo=TZ)
SUN = datetime(2026, 2,  8, tzinfo=TZ)

def dt(base: datetime, hour: int, minute: int = 0) -> datetime:
    """Return base date at given hour:minute."""
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Helper: build a coordinator from a flat config dict
# ---------------------------------------------------------------------------

def _make(data: dict) -> PeakMonitorCoordinator:
    """Construct a coordinator with mocked hass and minimal entry."""
    full = {
        "consumption_sensor": "sensor.power",
        "number_of_peaks": 3,
        "only_one_peak_per_day": True,
        "active_start_hour": 6,
        "active_end_hour": 22,
        "active_months": [str(m) for m in range(1, 13)],
        "daily_reduced_tariff_enabled": False,
        "reduced_start_hour": 22,
        "reduced_end_hour": 6,
        "reduced_also_on_weekends": False,
        "reduced_factor": 0.5,
        "weekend_behavior": "no_tariff",
        "weekend_start_hour": 6,
        "weekend_end_hour": 22,
        "holiday_behavior": "no_tariff",
        "holidays": [HOLIDAY_OFFICIAL, HOLIDAY_CHRISTMAS_EVE, HOLIDAY_NEW_YEARS_EVE],
    }
    full.update(data)

    entry = Mock()
    entry.entry_id = "test"
    entry.data = full
    entry.options = {}

    hass = Mock()
    hass.data = {}
    hass.states.get = Mock(return_value=None)

    return PeakMonitorCoordinator(hass, entry)


# ===========================================================================
# Ellevio
# ===========================================================================
# Config:
#   number_of_peaks       = 3
#   only_one_peak_per_day = True
#   active_start_hour     = 6
#   active_end_hour       = 22
#   active_months         = all (no seasonal restriction)
#   weekend_behavior      = full_tariff  (weekends count at full weight)
#   weekend_start_hour    = 6
#   weekend_end_hour      = 22
#   holiday_behavior      = no_tariff (conservative default; Ellevio is silent on this)
#   daily_reduced_tariff  = True
#   reduced_also_on_weekends = True     (ESSENTIAL — night rate every night)
#   reduced_start_hour    = 22
#   reduced_end_hour      = 6
#   reduced_factor        = 0.5
#
# Expected behaviour:
#   Mon–Sun 06–22  → ACTIVE   (full weight)
#   Mon–Sun 22–06  → REDUCED  (50% weight)
# ===========================================================================

class TestEllevio:
    """Ellevio: 3 peaks, no weekday/weekend split, night 22–06 = 50% every night."""

    def _coord(self):
        return _make({
            "number_of_peaks": 3,
            "only_one_peak_per_day": True,
            "active_start_hour": 6,
            "active_end_hour": 22,
            "active_months": [str(m) for m in range(1, 13)],
            "weekend_behavior": "full_tariff",
            "weekend_start_hour": 6,
            "weekend_end_hour": 22,
            "holiday_behavior": "no_tariff",
            "daily_reduced_tariff_enabled": True,
            "reduced_also_on_weekends": True,
            "reduced_start_hour": 22,
            "reduced_end_hour": 6,
            "reduced_factor": 0.5,
        })

    # --- Weekday ---
    def test_weekday_morning_active(self):
        assert self._coord().get_tariff_active_state(dt(MON, 8)) == ACTIVE_STATE_ON

    def test_weekday_evening_active(self):
        assert self._coord().get_tariff_active_state(dt(TUE, 18)) == ACTIVE_STATE_ON

    def test_weekday_night_reduced(self):
        assert self._coord().get_tariff_active_state(dt(MON, 23)) == ACTIVE_STATE_REDUCED

    def test_weekday_early_morning_reduced(self):
        assert self._coord().get_tariff_active_state(dt(TUE, 3)) == ACTIVE_STATE_REDUCED

    def test_weekday_at_active_start_is_active(self):
        """Hour 06 is the first active hour (reduced window ends at 06)."""
        assert self._coord().get_tariff_active_state(dt(MON, 6)) == ACTIVE_STATE_ON

    def test_weekday_at_reduced_start_is_reduced(self):
        """Hour 22 is the first reduced hour."""
        assert self._coord().get_tariff_active_state(dt(MON, 22)) == ACTIVE_STATE_REDUCED

    # --- Weekend — same as weekday for Ellevio ---
    def test_saturday_morning_active(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 10)) == ACTIVE_STATE_ON

    def test_saturday_afternoon_active(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 15)) == ACTIVE_STATE_ON

    def test_saturday_night_reduced(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 23)) == ACTIVE_STATE_REDUCED

    def test_sunday_early_morning_reduced(self):
        assert self._coord().get_tariff_active_state(dt(SUN, 4)) == ACTIVE_STATE_REDUCED

    def test_sunday_daytime_active(self):
        assert self._coord().get_tariff_active_state(dt(SUN, 12)) == ACTIVE_STATE_ON

    def test_outside_active_window_is_off(self):
        """Before 06 and after 22 on any day the tariff is reduced, not off."""
        # 05:59 → still in the reduced window (22–06), so REDUCED not OFF
        assert self._coord().get_tariff_active_state(dt(MON, 5)) == ACTIVE_STATE_REDUCED


# ===========================================================================
# Göteborg Energi Elnät
# ===========================================================================
# Config:
#   number_of_peaks       = 3
#   only_one_peak_per_day = True
#   active_start_hour     = 7
#   active_end_hour       = 20
#   active_months         = Nov Dec Jan Feb Mar
#   weekend_behavior      = no_tariff
#   holiday_behavior      = no_tariff
#   holidays              = official_holidays + christmas_eve + new_years_eve
#
# Expected behaviour:
#   Weekdays 07–20, Nov–Mar → ACTIVE
#   Nights, weekends, holidays, Apr–Oct → OFF
# ===========================================================================

class TestGoteborgEnergi:
    """Göteborg Energi: 3 peaks, weekdays 07–20, Nov–Mar, helger+röda dagar=noll."""

    WINTER_MONTHS = ["11", "12", "1", "2", "3"]

    def _coord(self):
        return _make({
            "number_of_peaks": 3,
            "active_start_hour": 7,
            "active_end_hour": 20,
            "active_months": self.WINTER_MONTHS,
            "weekend_behavior": "no_tariff",
            "holiday_behavior": "no_tariff",
            "holidays": [HOLIDAY_OFFICIAL, HOLIDAY_CHRISTMAS_EVE, HOLIDAY_NEW_YEARS_EVE],
        })

    def test_weekday_peak_hours_active(self):
        assert self._coord().get_tariff_active_state(dt(MON, 10)) == ACTIVE_STATE_ON

    def test_weekday_at_start_hour_active(self):
        assert self._coord().get_tariff_active_state(dt(MON, 7)) == ACTIVE_STATE_ON

    def test_weekday_before_start_is_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 6)) == ACTIVE_STATE_OFF

    def test_weekday_at_end_hour_is_off(self):
        """active_end_hour=20 means hour 20 is the first inactive hour (< 20)."""
        assert self._coord().get_tariff_active_state(dt(MON, 20)) == ACTIVE_STATE_OFF

    def test_weekday_night_is_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 23)) == ACTIVE_STATE_OFF

    def test_saturday_peak_hours_off(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 10)) == ACTIVE_STATE_OFF

    def test_sunday_off(self):
        assert self._coord().get_tariff_active_state(dt(SUN, 12)) == ACTIVE_STATE_OFF

    def test_summer_weekday_off(self):
        """April is outside active_months."""
        july_wed = datetime(2026, 7, 8, 10, tzinfo=TZ)  # Wednesday in July
        assert self._coord().get_tariff_active_state(july_wed) == ACTIVE_STATE_OFF

    def test_winter_weekday_in_range_active(self):
        """February weekday 09:00 should be active."""
        assert self._coord().get_tariff_active_state(dt(MON, 9)) == ACTIVE_STATE_ON


# ===========================================================================
# Vattenfall Eldistribution (effekttariff, 2025–2026 rollout)
# ===========================================================================
# Config:
#   number_of_peaks       = 5   (Vattenfall uses 5 highest peaks)
#   only_one_peak_per_day = True
#   active_start_hour     = 7
#   active_end_hour       = 21
#   active_months         = Nov Dec Jan Feb Mar
#   weekend_behavior      = no_tariff
#   holiday_behavior      = no_tariff
#   holidays              = official_holidays + christmas_eve + new_years_eve
#
# Source: "helgfria vardagar kl. 07–21, november till mars"
# ===========================================================================

class TestVattenfall:
    """Vattenfall: 5 peaks, helgfria vardagar 07–21, Nov–Mar."""

    WINTER_MONTHS = ["11", "12", "1", "2", "3"]

    def _coord(self):
        return _make({
            "number_of_peaks": 5,
            "active_start_hour": 7,
            "active_end_hour": 21,
            "active_months": self.WINTER_MONTHS,
            "weekend_behavior": "no_tariff",
            "holiday_behavior": "no_tariff",
            "holidays": [HOLIDAY_OFFICIAL, HOLIDAY_CHRISTMAS_EVE, HOLIDAY_NEW_YEARS_EVE],
        })

    def test_weekday_active_window_is_on(self):
        assert self._coord().get_tariff_active_state(dt(MON, 10)) == ACTIVE_STATE_ON

    def test_weekday_at_start_is_on(self):
        assert self._coord().get_tariff_active_state(dt(TUE, 7)) == ACTIVE_STATE_ON

    def test_weekday_before_start_is_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 6)) == ACTIVE_STATE_OFF

    def test_weekday_at_end_is_off(self):
        """active_end=21 → hour 21 is the first inactive hour."""
        assert self._coord().get_tariff_active_state(dt(MON, 21)) == ACTIVE_STATE_OFF

    def test_weekday_night_is_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 23)) == ACTIVE_STATE_OFF

    def test_saturday_is_off(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 10)) == ACTIVE_STATE_OFF

    def test_sunday_is_off(self):
        assert self._coord().get_tariff_active_state(dt(SUN, 14)) == ACTIVE_STATE_OFF

    def test_outside_active_months_is_off(self):
        june_wed = datetime(2026, 6, 3, 10, tzinfo=TZ)
        assert self._coord().get_tariff_active_state(june_wed) == ACTIVE_STATE_OFF


# ===========================================================================
# Tekniska verken (Linköping) — multiple peaks per day
# ===========================================================================
# Config:
#   number_of_peaks       = 5
#   only_one_peak_per_day = False  (multiple peaks per hour, any hour)
#   active_start_hour     = 6
#   active_end_hour       = 22    (or 0/0 for 24h — no explicit restriction)
#   active_months         = all
#   weekend_behavior      = full_tariff (weekends also count)
#   holiday_behavior      = no_tariff  (conservative default)
#
# Source: "fem högsta timmar per månad" — no weekday/seasonal restriction stated
# ===========================================================================

class TestTekniskaVerken:
    """Tekniska verken: 5 peaks, multiple per day, weekdays and weekends count."""

    def _coord(self):
        return _make({
            "number_of_peaks": 5,
            "only_one_peak_per_day": False,
            "active_start_hour": 6,
            "active_end_hour": 22,
            "active_months": [str(m) for m in range(1, 13)],
            "weekend_behavior": "full_tariff",
            "weekend_start_hour": 6,
            "weekend_end_hour": 22,
            "holiday_behavior": "no_tariff",
        })

    def test_weekday_peak_hours_active(self):
        assert self._coord().get_tariff_active_state(dt(MON, 10)) == ACTIVE_STATE_ON

    def test_saturday_also_active(self):
        """Weekends count for Tekniska verken."""
        assert self._coord().get_tariff_active_state(dt(SAT, 14)) == ACTIVE_STATE_ON

    def test_sunday_also_active(self):
        assert self._coord().get_tariff_active_state(dt(SUN, 10)) == ACTIVE_STATE_ON

    def test_weekday_outside_window_is_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 23)) == ACTIVE_STATE_OFF

    def test_weekend_outside_window_is_off(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 5)) == ACTIVE_STATE_OFF

    def test_summer_active(self):
        """No seasonal restriction — July should still be active."""
        july_tue = datetime(2026, 7, 7, 10, tzinfo=TZ)  # Tuesday
        assert self._coord().get_tariff_active_state(july_tue) == ACTIVE_STATE_ON


# ===========================================================================
# Jönköping Energi
# ===========================================================================
# Config:
#   number_of_peaks       = 2
#   only_one_peak_per_day = True
#   active_start_hour     = 7
#   active_end_hour       = 20
#   active_months         = Nov Dec Jan Feb Mar
#   weekend_behavior      = no_tariff
#   holiday_behavior      = no_tariff
# ===========================================================================

class TestJonkopingEnergi:
    """Jönköping Energi: 2 peaks, weekdays 07–20, Nov–Mar."""

    WINTER_MONTHS = ["11", "12", "1", "2", "3"]

    def _coord(self):
        return _make({
            "number_of_peaks": 2,
            "active_start_hour": 7,
            "active_end_hour": 20,
            "active_months": self.WINTER_MONTHS,
            "weekend_behavior": "no_tariff",
            "holiday_behavior": "no_tariff",
        })

    def test_weekday_in_window_active(self):
        assert self._coord().get_tariff_active_state(dt(MON, 9)) == ACTIVE_STATE_ON

    def test_weekday_before_window_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 6)) == ACTIVE_STATE_OFF

    def test_weekday_at_end_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 20)) == ACTIVE_STATE_OFF

    def test_weekend_off(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 10)) == ACTIVE_STATE_OFF

    def test_summer_off(self):
        aug_mon = datetime(2026, 8, 3, 10, tzinfo=TZ)
        assert self._coord().get_tariff_active_state(aug_mon) == ACTIVE_STATE_OFF


# ===========================================================================
# Umeå Energi
# ===========================================================================
# Config:
#   number_of_peaks       = 5
#   only_one_peak_per_day = True
#   active_start_hour     = 7
#   active_end_hour       = 20
#   active_months         = Nov Dec Jan Feb Mar
#   weekend_behavior      = no_tariff
#   holiday_behavior      = no_tariff
# ===========================================================================

class TestUmeaEnergi:
    """Umeå Energi: 5 peaks, weekdays 07–20, Nov–Mar."""

    WINTER_MONTHS = ["11", "12", "1", "2", "3"]

    def _coord(self):
        return _make({
            "number_of_peaks": 5,
            "active_start_hour": 7,
            "active_end_hour": 20,
            "active_months": self.WINTER_MONTHS,
            "weekend_behavior": "no_tariff",
            "holiday_behavior": "no_tariff",
        })

    def test_weekday_in_window_active(self):
        assert self._coord().get_tariff_active_state(dt(TUE, 12)) == ACTIVE_STATE_ON

    def test_weekday_at_start_active(self):
        assert self._coord().get_tariff_active_state(dt(MON, 7)) == ACTIVE_STATE_ON

    def test_weekday_at_end_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 20)) == ACTIVE_STATE_OFF

    def test_weekday_before_start_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 6)) == ACTIVE_STATE_OFF

    def test_saturday_off(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 10)) == ACTIVE_STATE_OFF

    def test_summer_off(self):
        sep_mon = datetime(2026, 9, 7, 10, tzinfo=TZ)
        assert self._coord().get_tariff_active_state(sep_mon) == ACTIVE_STATE_OFF

    def test_winter_weekday_active(self):
        nov_mon = datetime(2026, 11, 2, 10, tzinfo=TZ)
        assert self._coord().get_tariff_active_state(nov_mon) == ACTIVE_STATE_ON


# ===========================================================================
# Mälarenergi (Västerås)
# ===========================================================================
# Config:
#   number_of_peaks       = 1
#   only_one_peak_per_day = True
#   active_start_hour     = 6 (default — verify with your contract)
#   active_end_hour       = 22 (default — verify with your contract)
#   active_months         = all
#   weekend_behavior      = full_tariff (verify with your contract)
#   holiday_behavior      = no_tariff
#
# Only the single highest peak in the month counts.
# ===========================================================================

class TestMalarenergi:
    """Mälarenergi: 1 peak per month, full tariff all days (verify with contract)."""

    def _coord(self):
        return _make({
            "number_of_peaks": 1,
            "active_start_hour": 6,
            "active_end_hour": 22,
            "active_months": [str(m) for m in range(1, 13)],
            "weekend_behavior": "full_tariff",
            "weekend_start_hour": 6,
            "weekend_end_hour": 22,
            "holiday_behavior": "no_tariff",
        })

    def test_weekday_active(self):
        assert self._coord().get_tariff_active_state(dt(MON, 10)) == ACTIVE_STATE_ON

    def test_saturday_active(self):
        assert self._coord().get_tariff_active_state(dt(SAT, 14)) == ACTIVE_STATE_ON

    def test_outside_window_off(self):
        assert self._coord().get_tariff_active_state(dt(MON, 23)) == ACTIVE_STATE_OFF

    def test_summer_weekday_active(self):
        """No seasonal restriction."""
        aug_mon = datetime(2026, 8, 3, 10, tzinfo=TZ)
        assert self._coord().get_tariff_active_state(aug_mon) == ACTIVE_STATE_ON
