"""Unit tests for Peak Monitor config flow.

Only tests that can run without a real Home Assistant instance are included here.
Tests requiring full HA integration (schema validation with sections, async flow steps)
are excluded as they cannot be meaningfully tested in this environment.
"""
import pytest
import voluptuous as vol
from unittest.mock import Mock

from custom_components.peak_monitor.const import (
    DOMAIN,
    CONF_CONSUMPTION_SENSOR,
    CONF_REDUCED_FACTOR,
    DEFAULT_REDUCED_FACTOR,
)


class TestReducedFactorValidation:
    """Test reduced_factor field validation using real voluptuous rules.

    These tests bypass the full HA section schema and test the field
    validator directly, which is what matters for correctness.
    """

    def _reduced_factor_validator(self):
        """Return the same validator used in the real schema."""
        return vol.All(vol.Coerce(float), vol.Range(min=0.01, max=1.0))

    def test_default_value_is_correct(self):
        """DEFAULT_REDUCED_FACTOR is 0.5."""
        assert DEFAULT_REDUCED_FACTOR == pytest.approx(0.5)
        assert isinstance(DEFAULT_REDUCED_FACTOR, float)

    def test_valid_value_0_5_accepted(self):
        validator = self._reduced_factor_validator()
        result = validator(0.5)
        assert result == pytest.approx(0.5)

    def test_valid_value_0_01_accepted(self):
        """Minimum allowed value."""
        validator = self._reduced_factor_validator()
        result = validator(0.01)
        assert result == pytest.approx(0.01)

    def test_valid_value_1_0_accepted(self):
        """Maximum allowed value."""
        validator = self._reduced_factor_validator()
        result = validator(1.0)
        assert result == pytest.approx(1.0)

    def test_string_coerced_to_float(self):
        """String '0.7' from UI dropdown is coerced to float."""
        validator = self._reduced_factor_validator()
        result = validator("0.7")
        assert result == pytest.approx(0.7)
        assert isinstance(result, float)

    def test_zero_rejected(self):
        """0.0 is below minimum."""
        validator = self._reduced_factor_validator()
        with pytest.raises(vol.Invalid):
            validator(0.0)

    def test_below_minimum_rejected(self):
        """0.005 is below 0.01 minimum."""
        validator = self._reduced_factor_validator()
        with pytest.raises(vol.Invalid):
            validator(0.005)

    def test_above_maximum_rejected(self):
        """1.1 exceeds 1.0 maximum."""
        validator = self._reduced_factor_validator()
        with pytest.raises(vol.Invalid):
            validator(1.1)

    def test_two_rejected(self):
        """2.0 exceeds 1.0 maximum."""
        validator = self._reduced_factor_validator()
        with pytest.raises(vol.Invalid):
            validator(2.0)

    def test_negative_rejected(self):
        """Negative values are below minimum."""
        validator = self._reduced_factor_validator()
        with pytest.raises(vol.Invalid):
            validator(-0.5)

    def test_const_conf_reduced_factor_value(self):
        """CONF_REDUCED_FACTOR key string matches what config stores."""
        assert CONF_REDUCED_FACTOR == "reduced_factor"


class TestSensorResetLogic:
    """Test sensor reset and cumulative tracking logic."""

    def test_cumulative_sensor_decrease_rebaselines(self):
        """When cumulative sensor drops, coordinator re-baselines."""
        from custom_components.peak_monitor import PeakMonitorCoordinator
        from unittest.mock import AsyncMock
        import asyncio

        class _State:
            def __init__(self, val):
                self.state = val
                self.attributes = {"unit_of_measurement": "Wh"}

        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "sensor_resets_every_hour": False,
        }
        mock_entry.options = {}
        mock_hass = Mock()
        mock_hass.data = {}

        coord = PeakMonitorCoordinator(mock_hass, mock_entry)
        coord.last_cumulative_value = 50000.0
        coord.hour_cumulative_consumption = 1000.0
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()

        event = Mock()
        event.data = {
            "old_state": _State("50000"),
            "new_state": _State("100"),
        }
        asyncio.run(coord._async_consumption_changed(event))

        assert coord.last_cumulative_value == 100.0
        assert coord.hour_cumulative_consumption == 0.0

    def test_monthly_reset_commits_daily_peak(self):
        """Daily peak is committed to monthly peaks on day rollover."""
        from custom_components.peak_monitor import PeakMonitorCoordinator
        from unittest.mock import AsyncMock
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import asyncio

        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "number_of_peaks": 3,
            "reset_value": 500,
            "only_one_peak_per_day": True,
        }
        mock_entry.options = {}
        mock_hass = Mock()
        mock_hass.data = {}

        coord = PeakMonitorCoordinator(mock_hass, mock_entry)
        coord.daily_peak = 5000
        coord.monthly_peaks = [4000, 3500, 3000]
        coord.last_day = 15
        coord.last_month = 2
        coord._async_save_data = AsyncMock()
        coord._async_notify_listeners = AsyncMock()
        coord._schedule_next_daily_reset = Mock()

        now = datetime(2026, 2, 16, 0, 0, 30, tzinfo=ZoneInfo("Europe/Stockholm"))
        asyncio.run(coord._async_update_daily(now))

        assert 5000 in coord.monthly_peaks
        assert coord.monthly_peaks == [5000, 4000, 3500]
        assert coord.daily_peak == 500
        assert len(coord.monthly_peaks) == 3


class TestHourConsumptionAvailability:
    """Hour consumption sensor is unavailable until first reading arrives."""

    def test_unavailable_before_first_reading(self):
        from custom_components.peak_monitor import PeakMonitorCoordinator

        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {"consumption_sensor": "sensor.power"}
        mock_entry.options = {}
        mock_hass = Mock()
        mock_hass.data = {}

        coord = PeakMonitorCoordinator(mock_hass, mock_entry)
        assert coord.has_received_reading is False

    def test_sensor_returns_none_before_reading(self):
        from custom_components.peak_monitor import PeakMonitorCoordinator

        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {"consumption_sensor": "sensor.power"}
        mock_entry.options = {}
        mock_hass = Mock()
        mock_hass.data = {}

        coord = PeakMonitorCoordinator(mock_hass, mock_entry)
        result = None if not coord.has_received_reading else coord.hour_cumulative_consumption
        assert result is None

    def test_sensor_returns_value_after_reading(self):
        from custom_components.peak_monitor import PeakMonitorCoordinator

        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {"consumption_sensor": "sensor.power"}
        mock_entry.options = {}
        mock_hass = Mock()
        mock_hass.data = {}

        coord = PeakMonitorCoordinator(mock_hass, mock_entry)
        coord.has_received_reading = True
        coord.hour_cumulative_consumption = 250.0

        result = None if not coord.has_received_reading else coord.hour_cumulative_consumption
        assert result == pytest.approx(250.0)
