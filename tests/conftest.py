"""pytest configuration and fixtures for Peak Monitor tests."""
import sys
from unittest.mock import Mock, MagicMock
from pathlib import Path

# Add custom_components to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

# Mock homeassistant modules before they're imported
sys.modules['homeassistant'] = MagicMock()
sys.modules['homeassistant.config_entries'] = MagicMock()
sys.modules['homeassistant.const'] = MagicMock()
sys.modules['homeassistant.core'] = MagicMock()
sys.modules['homeassistant.helpers'] = MagicMock()
sys.modules['homeassistant.helpers.event'] = MagicMock()
sys.modules['homeassistant.helpers.storage'] = MagicMock()
sys.modules['homeassistant.helpers.entity_platform'] = MagicMock()
sys.modules['homeassistant.helpers.selector'] = MagicMock()
sys.modules['homeassistant.helpers.restore_state'] = MagicMock()
sys.modules['homeassistant.data_entry_flow'] = MagicMock()

# Make data_entry_flow.section a real passthrough so voluptuous schema tests work
import homeassistant.data_entry_flow as _def
def _section_passthrough(schema, options=None):
    return schema
_def.section = _section_passthrough
_def.FlowResultType = MagicMock()
sys.modules['homeassistant.components'] = MagicMock()
sys.modules['homeassistant.components.sensor'] = MagicMock()
sys.modules['homeassistant.util'] = MagicMock()
sys.modules['homeassistant.util.dt'] = MagicMock()

# Import dt_util mock and set up necessary functions
import homeassistant.util.dt as dt_util
from datetime import datetime
from zoneinfo import ZoneInfo

def mock_now():
    return datetime.now(ZoneInfo("Europe/Stockholm"))

dt_util.now = mock_now
dt_util.as_local = lambda dt: dt.astimezone(ZoneInfo("Europe/Stockholm"))

# Import and set up constants that tests might need
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
UnitOfEnergy.WATT_HOUR = "Wh"
UnitOfEnergy.KILO_WATT_HOUR = "kWh"
UnitOfPower.WATT = "W"
UnitOfPower.KILO_WATT = "kW"

from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass
SensorStateClass.MEASUREMENT = "measurement"
SensorStateClass.TOTAL = "total"
SensorStateClass.TOTAL_INCREASING = "total_increasing"
SensorDeviceClass.ENERGY = "energy"
SensorDeviceClass.POWER = "power"
SensorDeviceClass.MONETARY = "monetary"

# Mock Platform
from homeassistant.const import Platform
Platform.SENSOR = "sensor"
