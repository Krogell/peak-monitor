"""Test the reset_peak service call."""
import asyncio
from unittest.mock import Mock, AsyncMock

import pytest

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import ACTIVE_STATE_ON


def make_coordinator(peaks=None, reset_value=500) -> PeakMonitorCoordinator:
    mock_entry = Mock()
    mock_entry.entry_id = "test"
    mock_entry.data = {
        "consumption_sensor": "sensor.power",
        "reset_value": reset_value,
    }
    mock_entry.options = {}
    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states.get = Mock(return_value=None)
    coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
    coordinator._async_save_data = AsyncMock()
    coordinator._async_notify_listeners = AsyncMock()
    if peaks is not None:
        coordinator.monthly_peaks = list(peaks)
    return coordinator


def run_service(hass_data: dict, call_data: dict):
    """Simulate the service handler logic (mirrors _register_services handler)."""
    peak_index = call_data.get("peak_index")
    reset_to = call_data.get("reset_value")

    for entry_id, coordinator in hass_data.items():
        if peak_index is None:
            indices = list(range(len(coordinator.monthly_peaks)))
        else:
            idx = int(peak_index) - 1
            if idx < 0 or idx >= len(coordinator.monthly_peaks):
                continue
            indices = [idx]

        base_reset = coordinator.reset_value if reset_to is None else float(reset_to)

        for i in indices:
            current = coordinator.monthly_peaks[i]
            effective_reset = min(base_reset, current)
            coordinator.monthly_peaks[i] = effective_reset

        coordinator._force_update_target()
        asyncio.run(coordinator._async_save_data())
        asyncio.run(coordinator._async_notify_listeners())


class TestResetPeakService:
    """Tests for the reset_peak service handler."""

    def test_reset_single_peak(self):
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        run_service({"test": coordinator}, {"peak_index": 1})

        assert coordinator.monthly_peaks[0] == coordinator.reset_value
        assert coordinator.monthly_peaks[1] == 1200
        assert coordinator.monthly_peaks[2] == 1000

    def test_reset_all_peaks(self):
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        run_service({"test": coordinator}, {})

        assert all(p == coordinator.reset_value for p in coordinator.monthly_peaks)

    def test_reset_with_custom_value(self):
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        run_service({"test": coordinator}, {"peak_index": 2, "reset_value": 800})

        assert coordinator.monthly_peaks[0] == 1500
        assert coordinator.monthly_peaks[1] == 800
        assert coordinator.monthly_peaks[2] == 1000

    def test_safeguard_reset_value_cannot_exceed_current(self):
        """Reset value higher than current peak is silently clamped to current."""
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        run_service({"test": coordinator}, {"peak_index": 3, "reset_value": 9999})

        assert coordinator.monthly_peaks[2] == 1000

    def test_safeguard_reset_value_below_current_allowed(self):
        """Reset value below current peak is allowed."""
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        run_service({"test": coordinator}, {"peak_index": 1, "reset_value": 900})

        assert coordinator.monthly_peaks[0] == 900

    def test_reset_triggers_notify(self):
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        run_service({"test": coordinator}, {"peak_index": 1})

        coordinator._async_notify_listeners.assert_called_once()

    def test_reset_triggers_save(self):
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        run_service({"test": coordinator}, {"peak_index": 1})

        coordinator._async_save_data.assert_called_once()

    def test_reset_recalculates_target(self):
        """Target should be recalculated after a reset."""
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        coordinator.daily_peak = coordinator.reset_value
        run_service({"test": coordinator}, {"peak_index": 1})

        expected = max(coordinator.daily_peak, min(coordinator.monthly_peaks))
        assert coordinator.cached_target == expected

    def test_out_of_range_index_skipped(self):
        coordinator = make_coordinator(peaks=[1500, 1200, 1000])
        original = list(coordinator.monthly_peaks)
        run_service({"test": coordinator}, {"peak_index": 99})

        assert coordinator.monthly_peaks == original
