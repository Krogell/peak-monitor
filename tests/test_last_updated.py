"""Unit tests for last_updated attribute tracking in the coordinator and sensors."""
import ast
import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import ACTIVE_STATE_ON

TZ = ZoneInfo("Europe/Stockholm")

SENSOR_PY = Path(__file__).parent.parent / "custom_components" / "peak_monitor" / "sensor.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(extra: dict | None = None) -> Mock:
    data = {
        "consumption_sensor": "sensor.power",
        "sensor_resets_every_hour": True,
        "active_start_hour": 6,
        "active_end_hour": 21,
        "active_months": [str(m) for m in range(1, 13)],
        "number_of_peaks": 3,
        "only_one_peak_per_day": True,
        "holidays": [],
        "holiday_behavior": "no_tariff",
        "weekend_behavior": "no_tariff",
        "weekend_start_hour": 6,
        "weekend_end_hour": 21,
        "reset_value": 500,
        "price_per_kw": 100,
        "fixed_monthly_fee": 50,
        "output_unit": "W",
        "daily_reduced_tariff_enabled": False,
        "reduced_start_hour": 21,
        "reduced_end_hour": 6,
        "reduced_factor": 0.5,
    }
    if extra:
        data.update(extra)
    entry = Mock()
    entry.entry_id = "test_lu"
    entry.data = data
    entry.options = {}
    return entry


def _make_coordinator(extra: dict | None = None) -> PeakMonitorCoordinator:
    hass = Mock()
    hass.data = {}
    hass.states.get = Mock(return_value=None)
    return PeakMonitorCoordinator(hass, _make_entry(extra))


class _MockSensorState:
    def __init__(self, state: str = "1000"):
        self.state = state
        self.attributes = {"unit_of_measurement": "Wh"}


# ---------------------------------------------------------------------------
# Parse sensor.py to find all classes that override extra_state_attributes
# ---------------------------------------------------------------------------

def _parse_sensor_classes_with_last_updated() -> dict[str, bool]:
    """
    Parse sensor.py AST and return a dict of
    {class_name: has_last_updated_key} for every class that defines
    extra_state_attributes.
    """
    source = SENSOR_PY.read_text()
    tree = ast.parse(source)
    results = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not (
                isinstance(item, ast.FunctionDef)
                and item.name == "extra_state_attributes"
            ):
                continue
            has_key = any(
                isinstance(n, ast.Constant) and n.value == "last_updated"
                for n in ast.walk(item)
            )
            results[node.name] = has_key

    return results


# ---------------------------------------------------------------------------
# Source-level tests
# ---------------------------------------------------------------------------

class TestAllSensorsExposeLastUpdated:
    """Parse sensor.py and assert the right sensors expose/omit last_updated."""

    # Sensors that intentionally omit last_updated
    NO_LAST_UPDATED_SENSORS = {
        # Real-time computed sensors
        "PeakMonitorRelativeSensor",
        "PeakMonitorPercentageSensor",
        "PeakMonitorInternalEstimationSensor",
        "PeakMonitorCostIncreaseSensor",
        # Status sensor: changes every time state changes — not a useful change timestamp
        "PeakMonitorActiveSensor",
        # Hour consumption: changes every reading — not a meaningful change timestamp
        "PeakMonitorHourConsumptionSensor",
    }

    def test_every_extra_state_attributes_has_last_updated_key(self):
        """Non-exempt classes that define extra_state_attributes must include 'last_updated'."""
        results = _parse_sensor_classes_with_last_updated()
        assert results, "No sensor classes with extra_state_attributes found — check sensor.py path"
        missing = [
            cls for cls, ok in results.items()
            if not ok and cls not in self.NO_LAST_UPDATED_SENSORS
        ]
        assert not missing, (
            f"These sensor classes are missing 'last_updated' in extra_state_attributes: {missing}"
        )

    def test_exempt_sensors_do_not_have_last_updated(self):
        """Exempt sensors must NOT expose last_updated."""
        results = _parse_sensor_classes_with_last_updated()
        wrongly_present = [
            cls for cls in self.NO_LAST_UPDATED_SENSORS
            if results.get(cls) is True
        ]
        assert not wrongly_present, (
            f"These sensors should not expose 'last_updated': {wrongly_present}"
        )

    def test_expected_sensor_classes_with_last_updated_are_covered(self):
        """Verify sensors that SHOULD have last_updated are all present."""
        results = _parse_sensor_classes_with_last_updated()
        expected_with_last_updated = {
            "PeakMonitorSensor",
            "PeakMonitorCostSensor",
            "PeakMonitorTargetSensor",
            "PeakMonitorDailyPeakSensor",
            "PeakMonitorMonthlyPeakSensor",
        }
        missing = expected_with_last_updated - set(results.keys())
        assert not missing, f"These sensor classes were not found in sensor.py: {missing}"


# ---------------------------------------------------------------------------
# Coordinator initialisation
# ---------------------------------------------------------------------------

class TestLastUpdatedInit:
    """Verify all keys exist and are None on a fresh coordinator."""

    def test_all_keys_present(self):
        coord = _make_coordinator()
        for key in ("daily_peak", "monthly_peaks", "hour_consumption", "state", "target"):
            assert key in coord.last_updated, f"Missing key: {key}"

    def test_all_values_none_at_start(self):
        coord = _make_coordinator()
        for key, val in coord.last_updated.items():
            assert val is None, f"Expected None for '{key}', got {val}"


# ---------------------------------------------------------------------------
# State timestamp via _async_notify_listeners
# ---------------------------------------------------------------------------

class TestStateTimestamp:
    """last_updated['state'] is stamped every time listeners are notified."""

    def test_notify_stamps_state(self):
        coord = _make_coordinator()
        coord._listeners = []
        before = datetime.now(TZ)
        asyncio.run(coord._async_notify_listeners())
        after = datetime.now(TZ)
        ts = coord.last_updated["state"]
        assert ts is not None
        assert before <= ts <= after

    def test_notify_updates_state_monotonically(self):
        coord = _make_coordinator()
        coord._listeners = []
        asyncio.run(coord._async_notify_listeners())
        first = coord.last_updated["state"]
        asyncio.run(coord._async_notify_listeners())
        second = coord.last_updated["state"]
        assert second >= first


# ---------------------------------------------------------------------------
# Target timestamp
# ---------------------------------------------------------------------------

class TestTargetTimestamp:
    """last_updated['target'] is set only when the cached_target value changes."""

    def test_stamp_set_when_target_changes(self):
        coord = _make_coordinator()
        coord.daily_peak = 3000.0
        coord.monthly_peaks = [500.0, 500.0, 500.0]
        coord.cached_target = 500.0  # old value — will change to 3000
        coord.last_target_update_hour = None
        before = datetime.now(TZ)
        coord._force_update_target()
        after = datetime.now(TZ)
        ts = coord.last_updated["target"]
        assert ts is not None, "Expected target timestamp to be set when target changes"
        assert before <= ts <= after

    def test_stamp_not_set_when_target_unchanged(self):
        coord = _make_coordinator()
        coord.daily_peak = 500.0
        coord.monthly_peaks = [500.0, 500.0, 500.0]
        coord.cached_target = 500.0  # same value — no change expected
        coord.last_target_update_hour = None
        coord._force_update_target()
        assert coord.last_updated["target"] is None, (
            "Target timestamp should not be set when target value has not changed"
        )

    def test_stamp_updated_on_second_change(self):
        coord = _make_coordinator()
        coord.daily_peak = 2000.0
        coord.monthly_peaks = [500.0, 500.0, 500.0]
        coord.cached_target = 500.0
        coord.last_target_update_hour = None
        coord._force_update_target()
        first_ts = coord.last_updated["target"]
        assert first_ts is not None

        coord.daily_peak = 3000.0
        coord.last_target_update_hour = None
        coord._force_update_target()
        second_ts = coord.last_updated["target"]
        assert second_ts >= first_ts


# ---------------------------------------------------------------------------
# Daily peak timestamp
# ---------------------------------------------------------------------------

class TestDailyPeakTimestamp:
    """last_updated['daily_peak'] is set when daily_peak increases."""

    def _send_consumption(self, coord: PeakMonitorCoordinator, value: str) -> None:
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)
        event = Mock()
        event.data = {
            "old_state": _MockSensorState("0"),
            "new_state": _MockSensorState(value),
        }
        asyncio.run(coord._async_consumption_changed(event))

    def test_stamp_set_on_new_peak(self):
        coord = _make_coordinator()
        assert coord.last_updated["daily_peak"] is None
        before = datetime.now(TZ)
        self._send_consumption(coord, "2000")
        after = datetime.now(TZ)
        ts = coord.last_updated["daily_peak"]
        assert ts is not None, "Expected daily_peak timestamp to be set"
        assert before <= ts <= after

    def test_not_stamped_when_below_existing_peak(self):
        coord = _make_coordinator()
        coord.daily_peak = 5000.0
        self._send_consumption(coord, "100")
        assert coord.last_updated["daily_peak"] is None


# ---------------------------------------------------------------------------
# Monthly peaks timestamp
# ---------------------------------------------------------------------------

class TestMonthlyPeaksTimestamp:
    """last_updated['monthly_peaks'] is set when monthly_peaks changes."""

    def test_stamped_in_multiple_peaks_mode(self):
        coord = _make_coordinator(extra={"only_one_peak_per_day": False})
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord._schedule_next_daily_reset = Mock()
        coord.hour_cumulative_consumption = 9999.0
        coord.monthly_peaks = [500, 500, 500]
        before = datetime.now(TZ)
        asyncio.run(coord._async_update_hourly(datetime(2026, 1, 7, 14, 0, 0, tzinfo=TZ)))
        after = datetime.now(TZ)
        ts = coord.last_updated["monthly_peaks"]
        assert ts is not None, "Expected monthly_peaks timestamp to be set"
        assert before <= ts <= after

    def test_not_stamped_when_below_threshold(self):
        coord = _make_coordinator(extra={"only_one_peak_per_day": False})
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord._schedule_next_daily_reset = Mock()
        coord.hour_cumulative_consumption = 1.0
        coord.monthly_peaks = [9000, 9000, 9000]
        asyncio.run(coord._async_update_hourly(datetime(2026, 1, 7, 14, 0, 0, tzinfo=TZ)))
        assert coord.last_updated["monthly_peaks"] is None

    def test_stamped_on_daily_commit(self):
        coord = _make_coordinator()
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord._schedule_next_daily_reset = Mock()
        coord.daily_peak = 9000.0
        coord.monthly_peaks = [500, 500, 500]
        coord.last_month = datetime.now(TZ).month
        coord.last_day = datetime.now(TZ).day
        before = datetime.now(TZ)
        asyncio.run(coord._async_update_daily(datetime(2026, 1, 7, 14, 0, 0, tzinfo=TZ)))
        after = datetime.now(TZ)
        ts = coord.last_updated["monthly_peaks"]
        assert ts is not None, "Expected monthly_peaks timestamp to be set"
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# Hour consumption timestamp (coordinator internal — not exposed in sensor)
# ---------------------------------------------------------------------------

class TestHourConsumptionTimestamp:
    """last_updated['interval_consumption'] is still tracked internally by the coordinator."""

    def test_stamped_on_consumption_update(self):
        coord = _make_coordinator()
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)
        event = Mock()
        event.data = {
            "old_state": _MockSensorState("0"),
            "new_state": _MockSensorState("800"),
        }
        before = datetime.now(TZ)
        asyncio.run(coord._async_consumption_changed(event))
        after = datetime.now(TZ)
        ts = coord.last_updated["hour_consumption"]
        assert ts is not None, "Expected hour_consumption timestamp to be set"
        assert before <= ts <= after

    def test_stamped_on_hour_reset(self):
        coord = _make_coordinator()
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord._schedule_next_daily_reset = Mock()
        coord.hour_cumulative_consumption = 500.0
        before = datetime.now(TZ)
        asyncio.run(coord._async_update_hourly(datetime(2026, 1, 7, 14, 0, 0, tzinfo=TZ)))
        after = datetime.now(TZ)
        ts = coord.last_updated["hour_consumption"]
        assert ts is not None
        assert before <= ts <= after
        assert coord.hour_cumulative_consumption == 0.0


# ---------------------------------------------------------------------------
# Monthly average "today" marker — tested via coordinator state directly
# (sensor.py's extra_state_attributes is a thin wrapper; HA base classes
#  cannot be instantiated in the mock environment used by this test suite)
# ---------------------------------------------------------------------------

class TestMonthlyAverageTodayMarker:
    """Verify the today-marker logic used by PeakMonitorSensor.extra_state_attributes.

    The sensor property delegates to coordinator state + pure sorting logic.
    We test that logic here rather than instantiating the HA sensor class.
    """

    def _compute_attrs(self, monthly_peaks, daily_peak):
        """Replicate the sensor's peak-list + is_today logic for a given state."""
        today_in_tariff = daily_peak > min(monthly_peaks)
        if today_in_tariff:
            effective_peaks = sorted(monthly_peaks + [daily_peak], reverse=True)[:len(monthly_peaks)]
        else:
            effective_peaks = sorted(monthly_peaks, reverse=True)
        result = {"includes_today": today_in_tariff}
        for i, peak in enumerate(effective_peaks, 1):
            is_today = today_in_tariff and abs(peak - daily_peak) < 0.01
            result[f"monthly_peak_{i}"] = peak
            result[f"monthly_peak_{i}_is_today"] = is_today
        return result

    def test_today_marker_set_when_daily_peak_included(self):
        attrs = self._compute_attrs([1000.0, 800.0, 600.0], daily_peak=1200.0)
        assert attrs["monthly_peak_1_is_today"] is True
        assert attrs["monthly_peak_2_is_today"] is False
        assert attrs["monthly_peak_3_is_today"] is False

    def test_today_marker_not_set_when_daily_peak_below_min(self):
        attrs = self._compute_attrs([1000.0, 800.0, 600.0], daily_peak=400.0)
        assert attrs["monthly_peak_1_is_today"] is False
        assert attrs["monthly_peak_2_is_today"] is False
        assert attrs["monthly_peak_3_is_today"] is False

    def test_today_marker_in_middle_position(self):
        attrs = self._compute_attrs([1000.0, 800.0, 600.0], daily_peak=900.0)
        assert attrs["monthly_peak_1_is_today"] is False
        assert attrs["monthly_peak_2_is_today"] is True   # 900 is 2nd highest
        assert attrs["monthly_peak_3_is_today"] is False


# ---------------------------------------------------------------------------
# "now" sentinel for uncommitted live changes — tested via coordinator methods
# ---------------------------------------------------------------------------

class TestLastUpdatedNowSentinel:
    """last_updated reports 'now' when a sensor's value is being actively affected
    by uncommitted data.  All three sensor properties delegate to coordinator helper
    methods, so we test those methods directly here.
    """

    # -- is_monthly_average_affecting_now (used by Running Average + Cost sensors) --

    def test_monthly_avg_affecting_now_when_daily_peak_exceeds_min(self):
        coord = _make_coordinator()
        coord.monthly_peaks = [1000.0, 800.0, 600.0]
        coord.daily_peak = 900.0   # > min(600) → affecting
        assert coord.is_monthly_average_affecting_now() is True

    def test_monthly_avg_not_affecting_when_daily_peak_below_min(self):
        coord = _make_coordinator()
        coord.monthly_peaks = [1000.0, 800.0, 600.0]
        coord.daily_peak = 400.0   # < min(600) → not affecting
        assert coord.is_monthly_average_affecting_now() is False

    def test_monthly_avg_last_updated_logic_when_affecting(self):
        """Replicate the sensor attribute expression when affecting_now is True."""
        coord = _make_coordinator()
        coord.monthly_peaks = [1000.0, 800.0, 600.0]
        coord.daily_peak = 900.0
        affecting_now = coord.is_monthly_average_affecting_now()
        last_updated = "now" if affecting_now else coord.last_updated.get("monthly_peaks")
        assert last_updated == "now"

    def test_monthly_avg_last_updated_logic_when_not_affecting(self):
        coord = _make_coordinator()
        coord.monthly_peaks = [1000.0, 800.0, 600.0]
        coord.daily_peak = 400.0
        coord.last_updated["monthly_peaks"] = datetime(2026, 3, 1, 12, 0, 0, tzinfo=TZ)
        affecting_now = coord.is_monthly_average_affecting_now()
        last_updated = "now" if affecting_now else coord.last_updated.get("monthly_peaks")
        assert last_updated == datetime(2026, 3, 1, 12, 0, 0, tzinfo=TZ)

    # -- is_daily_peak_affecting_now (used by Daily Peak sensor) --

    def test_daily_peak_affecting_now_when_estimation_exceeds_peak(self):
        from unittest.mock import patch
        coord = _make_coordinator()
        coord.daily_peak = 1000.0
        with patch.object(coord, 'get_estimated_consumption', return_value=1200.0):
            with patch.object(coord, 'get_tariff_active_state', return_value='on'):
                assert coord.is_daily_peak_affecting_now() is True

    def test_daily_peak_not_affecting_when_estimation_below_peak(self):
        from unittest.mock import patch
        coord = _make_coordinator()
        coord.daily_peak = 1000.0
        with patch.object(coord, 'get_estimated_consumption', return_value=800.0):
            with patch.object(coord, 'get_tariff_active_state', return_value='on'):
                assert coord.is_daily_peak_affecting_now() is False

    def test_daily_peak_last_updated_logic_when_affecting(self):
        from unittest.mock import patch
        coord = _make_coordinator()
        coord.daily_peak = 1000.0
        with patch.object(coord, 'get_estimated_consumption', return_value=1200.0):
            with patch.object(coord, 'get_tariff_active_state', return_value='on'):
                affecting = coord.is_daily_peak_affecting_now()
        last_updated = "now" if affecting else coord.last_updated.get("daily_peak")
        assert last_updated == "now"

    def test_daily_peak_last_updated_logic_when_not_affecting(self):
        from unittest.mock import patch
        coord = _make_coordinator()
        coord.daily_peak = 1000.0
        coord.last_updated["daily_peak"] = datetime(2026, 3, 3, 8, 0, 0, tzinfo=TZ)
        with patch.object(coord, 'get_estimated_consumption', return_value=800.0):
            with patch.object(coord, 'get_tariff_active_state', return_value='on'):
                affecting = coord.is_daily_peak_affecting_now()
        last_updated = "now" if affecting else coord.last_updated.get("daily_peak")
        assert last_updated == datetime(2026, 3, 3, 8, 0, 0, tzinfo=TZ)
