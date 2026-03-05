"""Test external mute sensor functionality."""
from datetime import datetime
from unittest.mock import Mock, AsyncMock
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import ACTIVE_STATE_OFF, ACTIVE_STATE_ON


class MockState:
    """Mock Home Assistant state."""
    def __init__(self, entity_id: str, state: str = "off"):
        self.entity_id = entity_id
        self.state = state


class TestExternalMuteSensor:
    """Test external mute sensor functionality."""
    
    def test_external_mute_when_on(self):
        """Test that tariff is muted when external sensor is ON."""
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "external_mute_sensor": "binary_sensor.tariff_mute",
            "active_months": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        # External mute sensor is ON
        mock_hass.states.get = Mock(return_value=MockState("binary_sensor.tariff_mute", "on"))
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        
        # Test during what would normally be active time
        test_time = datetime(2026, 2, 11, 14, 0, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        state = coordinator.get_tariff_active_state(test_time)
        
        # Should be inactive due to external mute
        assert state == ACTIVE_STATE_OFF
        
        # Check reason
        state, reasons = coordinator.get_tariff_active_state_with_reasons(test_time)
        assert state == ACTIVE_STATE_OFF
        assert "external_mute" in reasons
    
    def test_external_mute_when_off(self):
        """Test normal operation when external sensor is OFF."""
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "external_mute_sensor": "binary_sensor.tariff_mute",
            "active_months": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
            "active_start_hour": 6,
            "active_end_hour": 21,
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        # External mute sensor is OFF
        mock_hass.states.get = Mock(return_value=MockState("binary_sensor.tariff_mute", "off"))
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        
        # Test during active hours
        test_time = datetime(2026, 2, 11, 14, 0, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        state = coordinator.get_tariff_active_state(test_time)
        
        # Should be active (normal operation)
        assert state == ACTIVE_STATE_ON
    
    def test_no_external_mute_sensor(self):
        """Test normal operation when no external mute sensor configured."""
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            # No external_mute_sensor configured
            "active_months": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
            "active_start_hour": 6,
            "active_end_hour": 21,
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        
        # Test during active hours
        test_time = datetime(2026, 2, 11, 14, 0, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        state = coordinator.get_tariff_active_state(test_time)
        
        # Should be active (normal operation)
        assert state == ACTIVE_STATE_ON
    
    def test_external_mute_overrides_everything(self):
        """Test that external mute takes priority over all other conditions."""
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "external_mute_sensor": "binary_sensor.tariff_mute",
            "active_months": ["2"],  # February only
            "active_start_hour": 6,
            "active_end_hour": 21,
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        # External mute sensor is ON
        mock_hass.states.get = Mock(return_value=MockState("binary_sensor.tariff_mute", "on"))
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        
        # Test during active month, active hours - should still be muted
        test_time = datetime(2026, 2, 11, 14, 0, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        state, reasons = coordinator.get_tariff_active_state_with_reasons(test_time)
        
        # Should be inactive due to external mute (not other reasons)
        assert state == ACTIVE_STATE_OFF
        assert "external_mute" in reasons
        assert "Excluded month" not in reasons  # Should not reach month check
    
    def test_external_mute_sensor_unavailable(self):
        """Test handling when external mute sensor is unavailable."""
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "external_mute_sensor": "binary_sensor.tariff_mute",
            "active_months": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
            "active_start_hour": 6,
            "active_end_hour": 21,
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        # External mute sensor returns None (unavailable)
        mock_hass.states.get = Mock(return_value=None)
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        
        # Test during active hours
        test_time = datetime(2026, 2, 11, 14, 0, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        state = coordinator.get_tariff_active_state(test_time)
        
        # Should be active (treat unavailable as not muted)
        assert state == ACTIVE_STATE_ON
