"""Test power sensor input (W/kW) — integral calculation."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import ACTIVE_STATE_ON, ACTIVE_STATE_OFF

TZ = ZoneInfo("Europe/Stockholm")


def make_power_coordinator(input_unit: str) -> PeakMonitorCoordinator:
    mock_entry = Mock()
    mock_entry.entry_id = "test"
    mock_entry.data = {
        "consumption_sensor": "sensor.power_w",
        "input_unit": input_unit,
    }
    mock_entry.options = {}
    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states.get = Mock(return_value=None)
    coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
    coordinator._async_save_data = AsyncMock()
    coordinator._async_notify_listeners = AsyncMock()
    coordinator.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)
    coordinator.consumption_sensor_available = True
    coordinator._input_unit_warned = True
    return coordinator


def make_event(value: str, unit: str = "W"):
    new_state = Mock()
    new_state.state = value
    new_state.attributes = {"unit_of_measurement": unit}
    old_state = Mock()
    old_state.state = "0"
    old_state.attributes = {}
    event = Mock()
    event.data = {"new_state": new_state, "old_state": old_state}
    return event


def run_event_at(coordinator, value: str, now: datetime):
    """Run a consumption event with dt_util.now() returning the given time."""
    import homeassistant.util.dt as dt_util
    event = make_event(value)
    with patch.object(dt_util, "now", return_value=now):
        asyncio.run(coordinator._async_handle_consumption_event(event))


class TestPowerInputIntegration:
    """Integration of W/kW input sensors into Wh consumption."""

    def test_first_reading_seeds_without_accumulation(self):
        coordinator = make_power_coordinator("W")
        t0 = datetime(2025, 3, 5, 10, 0, 0, tzinfo=TZ)
        run_event_at(coordinator, "1000", t0)

        # First reading seeds the sample; no Wh accumulated yet
        assert coordinator._last_power_sample is not None
        assert coordinator._power_integrated_wh == 0.0

    def test_two_readings_integrate_correctly(self):
        """Constant 1000 W over 30 minutes → 500 Wh."""
        coordinator = make_power_coordinator("W")
        t0 = datetime(2025, 3, 5, 10, 0, 0, tzinfo=TZ)
        t1 = datetime(2025, 3, 5, 10, 30, 0, tzinfo=TZ)

        run_event_at(coordinator, "1000", t0)   # seed
        run_event_at(coordinator, "1000", t1)   # integrate

        # 1000 W * 0.5 h = 500 Wh
        assert abs(coordinator._power_integrated_wh - 500.0) < 1.0

    def test_kw_input_converts_to_watts(self):
        """1.5 kW over 36 seconds → 15 Wh."""
        coordinator = make_power_coordinator("kW")
        t0 = datetime(2025, 3, 5, 10, 0, 0, tzinfo=TZ)
        t1 = datetime(2025, 3, 5, 10, 0, 36, tzinfo=TZ)

        run_event_at(coordinator, "1.5", t0)   # seed (1.5 kW = 1500 W)
        run_event_at(coordinator, "1.5", t1)   # integrate over 36 s

        # 1500 W * 36 s / 3600 = 15 Wh
        assert abs(coordinator._power_integrated_wh - 15.0) < 1.0

    def test_power_accumulator_resets_at_hour_boundary(self):
        coordinator = make_power_coordinator("W")
        coordinator._power_integrated_wh = 500.0
        t0 = datetime(2025, 3, 5, 10, 55, 0, tzinfo=TZ)
        coordinator._last_power_sample = (t0, 1000.0)

        now = datetime(2025, 3, 5, 11, 0, 0, tzinfo=TZ)
        asyncio.run(coordinator._async_update_hourly(now))

        assert coordinator._power_integrated_wh == 0.0
        assert coordinator._last_power_sample is None

    def test_hour_cumulative_reflects_integrated_wh(self):
        """hour_cumulative_consumption tracks integrated Wh for power inputs."""
        coordinator = make_power_coordinator("W")
        t0 = datetime(2025, 3, 5, 10, 0, 0, tzinfo=TZ)
        t1 = datetime(2025, 3, 5, 10, 15, 0, tzinfo=TZ)  # 15 min at 2000 W = 500 Wh

        run_event_at(coordinator, "2000", t0)
        run_event_at(coordinator, "2000", t1)

        assert abs(coordinator.hour_cumulative_consumption - 500.0) < 1.0
        assert abs(coordinator._power_integrated_wh - 500.0) < 1.0
