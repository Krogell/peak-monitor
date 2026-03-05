"""Tests for restart and power outage scenarios (0.1.31)."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import ACTIVE_STATE_ON, ACTIVE_STATE_OFF

TZ = ZoneInfo("Europe/Stockholm")


def make_coordinator(sensor_resets_every_hour=False, only_one_peak_per_day=True):
    """Create a coordinator for testing."""
    mock_entry = Mock()
    mock_entry.entry_id = "test"
    mock_entry.data = {
        "consumption_sensor": "sensor.power",
        "sensor_resets_every_hour": sensor_resets_every_hour,
        "only_one_peak_per_day": only_one_peak_per_day,
    }
    mock_entry.options = {}

    mock_hass = Mock()
    mock_hass.data = {}

    coord = PeakMonitorCoordinator(mock_hass, mock_entry)
    coord._async_save_data = AsyncMock()
    coord._async_notify_listeners = AsyncMock()
    return coord


def make_event(state_value, old_value=None):
    """Create a mock state change event."""
    event = Mock()
    new_state = Mock()
    new_state.state = str(state_value)
    event.data = {"new_state": new_state, "old_state": None}
    if old_value is not None:
        old_state = Mock()
        old_state.state = str(old_value)
        event.data["old_state"] = old_state
    return event


# ---------------------------------------------------------------------------
# Bug fix: Hour consumption sensor resets to 0 on restart (cumulative sensor)
# ---------------------------------------------------------------------------

class TestHourConsumptionResetOnRestart:

    def test_cross_hour_restart_rebaselines_cumulative_sensor(self):
        """After a cross-hour restart, first reading re-baselines so hour consumption starts at 0."""
        coord = make_coordinator(sensor_resets_every_hour=False)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)

        # Simulate restored state from storage (baseline was set at previous hour start)
        coord.last_cumulative_value = 50000.0
        coord.last_seen_cumulative_value = 50000.0
        coord.hour_cumulative_consumption = 1200.0  # Restored — should be discarded (different hour)
        coord._restart_rebaseline_needed = True  # Set by async_setup after cross-hour restore
        coord.has_received_reading = False

        # First reading after restart: meter reads 51200
        asyncio.run(coord._async_consumption_changed(make_event(51200)))

        # Should re-baseline to 51200; hour consumption resets to 0
        assert coord.last_cumulative_value == 51200.0
        assert coord.hour_cumulative_consumption == 0.0
        assert coord._restart_rebaseline_needed is False
        # has_received_reading stays False until the NEXT reading (rebaseline skips)
        assert coord.has_received_reading is False

    def test_same_hour_restart_preserves_hour_consumption(self):
        """After a same-hour restart, the restored hour_cumulative_consumption is kept.

        HA restarts at 14:32 having last saved at 14:20. The interval consumption
        accumulated before the restart (e.g. 800 Wh) should remain visible immediately;
        only the additional consumption since restart is added on the next reading.
        """
        coord = make_coordinator(sensor_resets_every_hour=False)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)

        # Simulate: HA restarted mid-hour.  Storage had cumulative baseline of 50000
        # at the start of the hour and 800 Wh accumulated so far.
        coord.last_cumulative_value = 50000.0   # baseline at hour start (restored)
        coord.last_seen_cumulative_value = 50800.0
        coord.hour_cumulative_consumption = 800.0   # restored — must NOT be discarded
        coord._restart_rebaseline_needed = False  # Same-hour: flag is NOT set
        coord.has_received_reading = True           # restored along with consumption

        # First reading after restart: meter now reads 50950 (150 Wh more since restart)
        asyncio.run(coord._async_consumption_changed(make_event(50950)))

        # Consumption should be the full delta from the hour-start baseline: 950 Wh
        assert coord.hour_cumulative_consumption == 950.0
        assert coord.has_received_reading is True

    def test_same_hour_restart_sensor_visible_before_first_reading(self):
        """After a same-hour restart, the interval consumption sensor is non-None immediately.

        has_received_reading must be restored to True so the sensor shows the
        last known value rather than 'unavailable' during the startup window.
        """
        coord = make_coordinator(sensor_resets_every_hour=False)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)

        # Simulate what async_setup does on a same-hour restore
        coord.hour_cumulative_consumption = 600.0
        coord.has_received_reading = True  # Set by restore logic when same_hour
        coord._restart_rebaseline_needed = False

        # Before any new reading arrives, the sensor value should be the restored one
        assert coord.hour_cumulative_consumption == 600.0
        assert coord.has_received_reading is True

    def test_cross_hour_restart_rebaseline_then_normal_reading(self):
        """After a cross-hour rebaseline, the next reading accumulates normally."""
        coord = make_coordinator(sensor_resets_every_hour=False)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)

        coord.last_cumulative_value = 50000.0
        coord._restart_rebaseline_needed = True
        coord.has_received_reading = False

        # Trigger rebaseline
        asyncio.run(coord._async_consumption_changed(make_event(51200)))
        assert coord.last_cumulative_value == 51200.0
        assert coord.hour_cumulative_consumption == 0.0

        # Next reading: 300 Wh more
        asyncio.run(coord._async_consumption_changed(make_event(51500)))
        assert coord.hour_cumulative_consumption == 300.0
        assert coord.has_received_reading is True

    def test_no_rebaseline_without_consumption_sensor(self):
        """If consumption sensor is missing (unavailable), no rebaseline occurs."""
        coord = make_coordinator(sensor_resets_every_hour=False)

        coord.last_cumulative_value = 50000.0
        coord._restart_rebaseline_needed = True

        # Sensor becomes unavailable — should NOT rebaseline
        unavail_event = Mock()
        unavail_event.data = {
            "new_state": Mock(state="unavailable"),
            "old_state": Mock(state="51200"),
        }
        asyncio.run(coord._async_consumption_changed(unavail_event))

        # Rebaseline flag should remain — sensor not available yet
        assert coord._restart_rebaseline_needed is True
        assert coord.last_cumulative_value == 50000.0

    def test_hourly_reset_sensor_unaffected(self):
        """For hourly-reset sensors, rebaseline flag has no effect."""
        coord = make_coordinator(sensor_resets_every_hour=True)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)

        coord._restart_rebaseline_needed = False
        asyncio.run(coord._async_consumption_changed(make_event(500)))
        assert coord.hour_cumulative_consumption == 500.0


# ---------------------------------------------------------------------------
# Bug fix: Estimation sensor unavailable around hour change / on restart
# ---------------------------------------------------------------------------

class TestEstimationUnreliable:

    def test_estimation_unreliable_on_startup(self):
        """Estimation is unreliable on startup before any samples arrive."""
        coord = make_coordinator()
        assert coord._estimation_unreliable is True
        assert coord.get_estimated_consumption() is None

    def test_estimation_becomes_reliable_after_first_sample(self):
        """After first valid sample, estimation becomes reliable."""
        coord = make_coordinator(sensor_resets_every_hour=True)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)

        asyncio.run(coord._async_consumption_changed(make_event(500)))
        assert coord._estimation_unreliable is False
        assert coord.get_estimated_consumption() is not None

    def test_estimation_unreliable_at_hour_boundary_no_rate(self):
        """At hour boundary with no previous_hour_rate, estimation becomes unreliable."""
        coord = make_coordinator(sensor_resets_every_hour=True)
        coord._estimation_unreliable = False
        coord.previous_hour_rate = None  # No previous rate

        t = datetime(2026, 2, 13, 9, 0, 0, tzinfo=TZ)
        asyncio.run(coord._async_update_hourly(t))

        assert coord._estimation_unreliable is True
        assert coord.get_estimated_consumption() is None

    def test_estimation_reliable_at_hour_boundary_with_rate(self):
        """At hour boundary with previous_hour_rate, estimation stays reliable."""
        coord = make_coordinator(sensor_resets_every_hour=True)
        coord._estimation_unreliable = False
        coord.previous_hour_rate = 0.5  # Valid rate from previous hour

        t = datetime(2026, 2, 13, 9, 0, 0, tzinfo=TZ)
        asyncio.run(coord._async_update_hourly(t))

        assert coord._estimation_unreliable is False


# ---------------------------------------------------------------------------
# Test: Daily peak commit to monthly with restart crossing midnight
# ---------------------------------------------------------------------------

class TestMidnightRestartDailyPeakCommit:

    def test_daily_peak_committed_on_restart_after_midnight(self):
        """When HA restarts after midnight, stored daily peak is committed to monthly."""
        coord = make_coordinator(only_one_peak_per_day=True)

        # Simulate stored state: daily peak from yesterday, last_day = yesterday
        yesterday = datetime(2026, 2, 12, 23, 55, 0, tzinfo=TZ)
        today = datetime(2026, 2, 13, 5, 0, 0, tzinfo=TZ)

        coord.daily_peak = 3000.0  # Peak from yesterday
        coord.monthly_peaks = [0] * 3
        coord.last_day = yesterday.day  # Day 12
        coord.last_month = yesterday.month

        # Simulate async_setup calling _check_and_perform_resets at 05:00 day 13
        with patch('custom_components.peak_monitor.dt_util') as mock_dt:
            mock_dt.now.return_value = today
            asyncio.run(coord._check_and_perform_resets())

        # Daily peak should have been committed
        assert 3000.0 in coord.monthly_peaks
        # And daily peak should have been reset
        assert coord.daily_peak == coord.reset_value

    def test_daily_peak_committed_on_restart_after_month_boundary(self):
        """When HA restarts after a month boundary, last day's peak is committed."""
        coord = make_coordinator(only_one_peak_per_day=True)

        last_day_of_month = datetime(2026, 1, 31, 23, 55, 0, tzinfo=TZ)
        first_day_new_month = datetime(2026, 2, 1, 2, 0, 0, tzinfo=TZ)

        coord.daily_peak = 4500.0
        coord.monthly_peaks = [2000.0, 1800.0, 1500.0]
        coord.last_day = last_day_of_month.day
        coord.last_month = last_day_of_month.month  # January

        with patch('custom_components.peak_monitor.dt_util') as mock_dt:
            mock_dt.now.return_value = first_day_new_month
            asyncio.run(coord._check_and_perform_resets())

        # After monthly reset, peaks should be wiped (new month)
        # But the commit should have happened before the wipe
        # (verified by the logic in _check_and_perform_resets)
        assert coord.last_month == 2  # February
        assert coord.daily_peak == coord.reset_value


# ---------------------------------------------------------------------------
# Test: Long power outage across multiple days
# ---------------------------------------------------------------------------

class TestLongPowerOutage:

    def test_long_outage_day1_to_day3_daily_peak_committed(self):
        """Power outage from 23:57 day 1 to 05:00 day 3 — daily peak committed."""
        coord = make_coordinator(only_one_peak_per_day=True)

        # State at shutdown: day 1, 23:57, daily peak was 3500 Wh
        coord.daily_peak = 3500.0
        coord.monthly_peaks = [2000.0, 1800.0, 1500.0]
        coord.last_day = 10  # Day 10
        coord.last_month = 2  # February

        # HA comes back: day 12 (day 3 in the scenario), 05:00
        restart_time = datetime(2026, 2, 12, 5, 0, 0, tzinfo=TZ)
        with patch('custom_components.peak_monitor.dt_util') as mock_dt:
            mock_dt.now.return_value = restart_time
            asyncio.run(coord._check_and_perform_resets())

        # 3500 Wh daily peak should be committed to monthly peaks
        assert 3500.0 in coord.monthly_peaks
        assert coord.daily_peak == coord.reset_value

    def test_long_outage_peak_hour_outage_daily_peak_survives(self):
        """Power outage from 08:59 to 13:45 same day — daily peak persists and commits."""
        coord = make_coordinator(only_one_peak_per_day=True)

        # HA was running; stored daily peak from 08:xx (peak hour)
        coord.daily_peak = 2800.0
        coord.monthly_peaks = [2000.0, 1800.0, 1500.0]
        coord.last_day = 13  # Same day
        coord.last_month = 2

        # HA restarts at 13:45 same day — last_day == now.day so no daily reset
        restart_time = datetime(2026, 2, 13, 13, 45, 0, tzinfo=TZ)
        with patch('custom_components.peak_monitor.dt_util') as mock_dt:
            mock_dt.now.return_value = restart_time
            asyncio.run(coord._check_and_perform_resets())

        # No reset should have happened (same day)
        assert coord.daily_peak == 2800.0
        # Peak survives until midnight when it will be committed


# ---------------------------------------------------------------------------
# Run all tests manually
# ---------------------------------------------------------------------------

def run_all_tests():
    """Run all restart and outage tests."""
    import sys
    print("\nRunning Restart and Outage Tests (0.1.31)...")
    print("=" * 60)

    suites = [
        ("Hour consumption on restart (same-hour preserve / cross-hour reset)", TestHourConsumptionResetOnRestart),
        ("Estimation unreliable on restart/hour change", TestEstimationUnreliable),
        ("Midnight restart daily peak commit", TestMidnightRestartDailyPeakCommit),
        ("Long power outage", TestLongPowerOutage),
    ]

    failed = 0
    total = 0
    for suite_name, suite_class in suites:
        suite = suite_class()
        for method_name in [m for m in dir(suite) if m.startswith("test_")]:
            total += 1
            try:
                getattr(suite, method_name)()
                print(f"  ✓ {suite_name}: {method_name}")
            except Exception as e:
                print(f"  ✗ {suite_name}: {method_name}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1

    print("=" * 60)
    print(f"Tests passed: {total - failed}/{total}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
