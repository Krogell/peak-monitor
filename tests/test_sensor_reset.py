"""Test sensor reset detection logic for cumulative sensors."""
from datetime import datetime
from unittest.mock import Mock, AsyncMock
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import ACTIVE_STATE_ON


class MockState:
    """Mock Home Assistant state."""
    def __init__(self, entity_id: str, state: str = "0"):
        self.entity_id = entity_id
        self.state = state


class TestSensorResetDetection:
    """Test sensor reset detection for cumulative sensors."""
    
    def test_cumulative_sensor_monthly_reset_detected(self):
        """Test that monthly reset is detected when sensor_resets_every_hour is False."""
        import asyncio
        
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "sensor_resets_every_hour": False,  # Cumulative sensor
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        coordinator._async_save_data = AsyncMock()
        coordinator._async_notify_listeners = AsyncMock()
        coordinator.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)
        
        # Set up initial state - sensor at 50000 Wh
        coordinator.last_cumulative_value = 50000.0
        coordinator.last_seen_cumulative_value = 50000.0
        
        # Simulate monthly reset - sensor now reads 1000 Wh (reset occurred)
        mock_event = Mock()
        mock_event.data = {
            "old_state": MockState("sensor.power", "50000"),
            "new_state": MockState("sensor.power", "1000")
        }
        
        asyncio.run(coordinator._async_consumption_changed(mock_event))
        
        # Should detect reset and re-baseline
        assert coordinator.last_cumulative_value == 1000.0
        assert coordinator.last_seen_cumulative_value == 1000.0
        assert coordinator.hour_cumulative_consumption == 0.0  # Should be reset
    
    def test_cumulative_sensor_hour_boundary_reset_detected(self):
        """Test that reset at hour boundary is detected and logged."""
        import asyncio
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "sensor_resets_every_hour": False,  # Cumulative sensor
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        mock_hass.states.get = Mock(return_value=MockState("sensor.power", "500"))
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        coordinator._async_save_data = AsyncMock()
        coordinator._async_notify_listeners = AsyncMock()
        
        # Set up state before hour boundary
        coordinator.last_cumulative_value = 50000.0
        coordinator.last_seen_cumulative_value = 50000.0
        
        # Simulate hour boundary update - sensor has reset to 500
        test_time = datetime(2026, 2, 13, 15, 0, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        with patch('custom_components.peak_monitor._LOGGER') as mock_logger:
            asyncio.run(coordinator._async_update_hourly(test_time))
            
            # Should detect reset and log it
            mock_logger.info.assert_called()
            assert coordinator.last_cumulative_value == 500.0
            assert coordinator.last_seen_cumulative_value == 500.0
    
    def test_cumulative_sensor_no_reset_normal_increment(self):
        """Test normal operation without reset when sensor increments normally."""
        import asyncio
        
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "sensor_resets_every_hour": False,  # Cumulative sensor
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        coordinator._async_save_data = AsyncMock()
        coordinator._async_notify_listeners = AsyncMock()
        coordinator.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)
        
        # Set up initial state - sensor at 50000 Wh
        coordinator.last_cumulative_value = 50000.0
        coordinator.last_seen_cumulative_value = 50000.0
        coordinator.hour_cumulative_consumption = 0.0
        
        # Normal increment - sensor now reads 52000 Wh (2000 Wh consumed)
        mock_event = Mock()
        mock_event.data = {
            "old_state": MockState("sensor.power", "50000"),
            "new_state": MockState("sensor.power", "52000")
        }
        
        asyncio.run(coordinator._async_consumption_changed(mock_event))
        
        # Should calculate consumption normally
        assert coordinator.hour_cumulative_consumption == 2000.0
        assert coordinator.last_seen_cumulative_value == 52000.0
        # last_cumulative_value stays at hour boundary until next hour
        assert coordinator.last_cumulative_value == 50000.0
    
    def test_hourly_reset_sensor_no_reset_detection_needed(self):
        """Test that hourly reset sensors don't need reset detection."""
        import asyncio
        
        mock_entry = Mock()
        mock_entry.entry_id = "test"
        mock_entry.data = {
            "consumption_sensor": "sensor.power",
            "sensor_resets_every_hour": True,  # Hourly reset sensor
        }
        mock_entry.options = {}
        
        mock_hass = Mock()
        mock_hass.data = {}
        
        coordinator = PeakMonitorCoordinator(mock_hass, mock_entry)
        coordinator._async_save_data = AsyncMock()
        coordinator._async_notify_listeners = AsyncMock()
        coordinator.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)
        
        # For hourly reset sensors, the value IS the consumption
        mock_event = Mock()
        mock_event.data = {
            "old_state": MockState("sensor.power", "2000"),
            "new_state": MockState("sensor.power", "100")  # Reset to low value
        }
        
        asyncio.run(coordinator._async_consumption_changed(mock_event))
        
        # Should just use the value directly - no reset detection needed
        # The sensor value of 100 means 100 Wh consumed this hour
        # (Test verifies no errors occur - reset detection is skipped)
        assert coordinator.last_cumulative_value is None  # Not used for hourly reset sensors


def run_all_tests():
    """Run all sensor reset tests."""
    print("\nRunning Sensor Reset Detection Tests...")
    print("=" * 60)
    
    import sys
    test_suite = TestSensorResetDetection()
    
    tests = [
        ("Monthly reset detection", test_suite.test_cumulative_sensor_monthly_reset_detected),
        ("Hour boundary reset detection", test_suite.test_cumulative_sensor_hour_boundary_reset_detected),
        ("Normal increment (no reset)", test_suite.test_cumulative_sensor_no_reset_normal_increment),
        ("Hourly reset sensor", test_suite.test_hourly_reset_sensor_no_reset_detection_needed),
    ]
    
    failed = 0
    for name, test_func in tests:
        try:
            test_func()
            print(f"✓ {name}")
        except Exception as e:
            print(f"✗ {name}: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Tests passed: {len(tests) - failed}/{len(tests)}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
