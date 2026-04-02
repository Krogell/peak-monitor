"""Test configurable currency for cost sensors."""
import pytest
from unittest.mock import Mock

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import DEFAULT_CURRENCY


def make_coordinator(currency: str) -> PeakMonitorCoordinator:
    mock_entry = Mock()
    mock_entry.entry_id = "test"
    mock_entry.data = {
        "consumption_sensor": "sensor.power",
        "currency": currency,
    }
    mock_entry.options = {}
    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states.get = Mock(return_value=None)
    return PeakMonitorCoordinator(mock_hass, mock_entry)


class TestCurrencyConfiguration:
    """Currency is stored on the coordinator and used by cost sensors."""

    def test_default_currency_is_sek(self):
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {"consumption_sensor": "sensor.power"}
        mock_entry.options = {}
        mock_hass = Mock()
        mock_hass.data = {}
        mock_hass.states.get = Mock(return_value=None)
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        assert coordinator.currency == "SEK"

    def test_eur_currency(self):
        coordinator = make_coordinator("EUR")
        assert coordinator.currency == "EUR"

    def test_usd_currency(self):
        coordinator = make_coordinator("USD")
        assert coordinator.currency == "USD"

    def test_custom_currency_stored(self):
        coordinator = make_coordinator("NOK")
        assert coordinator.currency == "NOK"

    def test_currency_used_in_price_unit_attribute(self):
        """The period average sensor should expose the configured currency."""
        coordinator = make_coordinator("EUR")
        coordinator.monthly_peaks = [1000, 900, 800]
        coordinator.daily_peak = 500
        coordinator.price_per_kw = 100.0
        coordinator.number_of_peaks = 3
        coordinator.reset_value = 500

        # Simulate what the sensor's extra_state_attributes returns
        tariff_wh = coordinator.get_current_tariff(include_today=False)
        price = coordinator.price_per_kw * tariff_wh / 1000

        attrs = {
            "price": round(price, 2),
            "price_unit": coordinator.currency,
        }

        assert attrs["price_unit"] == "EUR"
