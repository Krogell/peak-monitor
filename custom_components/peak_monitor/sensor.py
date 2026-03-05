"""Sensor platform for Peak Monitor integration."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from . import PeakMonitorCoordinator
from .const import (
    DOMAIN,
    SENSOR_TARIFF,
    SENSOR_TARGET,
    SENSOR_RELATIVE,
    SENSOR_DAILY_PEAK,
    SENSOR_PERCENTAGE,
    SENSOR_COST,
    SENSOR_COST_INCREASE,
    SENSOR_INTERNAL_ESTIMATION,
    SENSOR_HOUR_CONSUMPTION,
    SENSOR_INTERVAL_CONSUMPTION,
    SENSOR_ACTIVE,
    ACTIVE_STATE_OFF,
    ACTIVE_STATE_ON,
    ACTIVE_STATE_REDUCED,
    STATE_ACTIVE,
    STATE_REDUCED,
)
from .state_mapper import StateMapper
from .utils import apply_output_unit, output_precision

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Peak Monitor sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        PeakMonitorSensor(coordinator, entry),
        PeakMonitorTargetSensor(coordinator, entry),
        PeakMonitorRelativeSensor(coordinator, entry),
        PeakMonitorPercentageSensor(coordinator, entry),
        PeakMonitorActiveSensor(coordinator, entry),
    ]
    
    # Daily peak sensor - only in normal mode (only one peak per day)
    if coordinator.only_one_peak_per_day:
        entities.append(PeakMonitorDailyPeakSensor(coordinator, entry))

    # Cost sensors - only when price_per_kw is configured and > 0
    if coordinator.price_per_kw is not None and coordinator.price_per_kw > 0:
        entities.append(PeakMonitorCostSensor(coordinator, entry))
        entities.append(PeakMonitorCostIncreaseSensor(coordinator, entry))

    # Internal estimation sensor — only when no external sensor is configured
    if not coordinator.estimation_sensor:
        entities.append(PeakMonitorInternalEstimationSensor(coordinator, entry))

    # Hourly consumption sensor — when input is cumulative (non-resetting),
    # OR in multiple-peaks-per-day mode (where each hour is independently tracked)
    if not coordinator.sensor_resets_every_hour or not coordinator.only_one_peak_per_day:
        entities.append(PeakMonitorHourConsumptionSensor(coordinator, entry))

    # Individual monthly peak sensors
    for i in range(coordinator.number_of_peaks):
        entities.append(PeakMonitorMonthlyPeakSensor(coordinator, entry, i))

    async_add_entities(entities)


# ------------------------------------------------------------------
# Base class
# ------------------------------------------------------------------

class PeakMonitorBaseSensor(SensorEntity):
    """Base class for Peak Monitor sensors."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self.coordinator = coordinator
        self.entry = entry
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name", "Peak Monitor"),
            "manufacturer": "Krogell",
            "model": "Peak Monitor",
        }

    async def async_added_to_hass(self) -> None:
        """Register coordinator callback."""
        self.coordinator.add_listener(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        self.coordinator.remove_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    def _set_power_unit_attributes(self) -> None:
        """Apply the coordinator's output unit (W or kW) to this sensor."""
        ou = self.coordinator.output_unit
        if ou == "kW":
            self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
            self._attr_suggested_display_precision = 3
        else:
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_suggested_display_precision = 0


# ------------------------------------------------------------------
# Power tariff (average of top peaks)
# ------------------------------------------------------------------

class PeakMonitorSensor(PeakMonitorBaseSensor):
    """Sensor showing the current peak monitor tariff (average of top peaks)."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_TARIFF}"
        self._attr_translation_key = "running_average"
        self._update_unit_attributes()
        # total_increasing: average strictly increases within a month — new peaks only
        # enter when > min(monthly_peaks), which always raises the sum. Monthly reset
        # back to reset_value is treated by HA as a new meter cycle.
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_icon = "mdi:flash"
    
    def _update_unit_attributes(self) -> None:
        """Delegate to the shared base helper."""
        self._set_power_unit_attributes()

    @property
    def native_value(self) -> float:
        tariff_wh = self.coordinator.get_current_tariff(include_today=True)
        return round(self.coordinator._convert_to_output_unit(tariff_wh), 
                    self.coordinator.get_output_precision())

    @property
    def extra_state_attributes(self) -> dict:
        tariff_wh = self.coordinator.get_current_tariff(include_today=True)
        price = self.coordinator.price_per_kw * tariff_wh / 1000

        daily_peak = self.coordinator.daily_peak
        monthly_peaks = self.coordinator.monthly_peaks
        today_in_tariff = daily_peak > min(monthly_peaks)

        # "now" only when the live estimate is actively pushing the value higher
        # right now (estimate > daily_peak, tariff active). When today's peak is
        # already included but no longer climbing, show the real commit timestamp.
        actively_climbing = self.coordinator.is_daily_peak_affecting_now()
        if actively_climbing:
            last_updated = "now"
        elif today_in_tariff:
            last_updated = self.coordinator.last_updated.get("daily_peak")
        else:
            last_updated = self.coordinator.last_updated.get("monthly_peaks")

        attrs = {
            "price": round(price, 2),
            "price_unit": "SEK",
            "includes_today": today_in_tariff,
            "last_updated": last_updated,
        }

        precision = self.coordinator.get_output_precision()

        if today_in_tariff:
            # Build effective top-N peaks including today's daily peak
            effective_peaks = sorted(monthly_peaks + [daily_peak], reverse=True)[:len(monthly_peaks)]
        else:
            effective_peaks = sorted(monthly_peaks, reverse=True)

        for i, peak in enumerate(effective_peaks, 1):
            converted_peak = self.coordinator._convert_to_output_unit(peak)
            is_today = today_in_tariff and abs(peak - daily_peak) < 0.01
            attrs[f"monthly_peak_{i}"] = round(converted_peak, precision)
            attrs[f"monthly_peak_{i}_is_today"] = is_today

        return attrs


# ------------------------------------------------------------------
# Monthly power grid fee
# ------------------------------------------------------------------

class PeakMonitorCostSensor(PeakMonitorBaseSensor):
    """Sensor showing the estimated monthly power grid fee in SEK."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_COST}"
        self._attr_translation_key = "power_grid_peak_tariff"
        self._attr_native_unit_of_measurement = "SEK"
        self._attr_state_class = SensorStateClass.TOTAL
        # total: MONETARY device class only allows 'total'. The fee tracks the monthly
        # average which is non-decreasing within a month, and resets monthly.
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_icon = "mdi:cash"
        self._attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float:
        tariff_wh = self.coordinator.get_current_tariff(include_today=True)
        cost = self.coordinator.price_per_kw * (tariff_wh / 1000) + self.coordinator.fixed_monthly_fee
        return round(cost, 2)

    @property
    def extra_state_attributes(self) -> dict:
        actively_climbing = self.coordinator.is_daily_peak_affecting_now()
        today_in_tariff = self.coordinator.is_monthly_average_affecting_now()
        if actively_climbing:
            last_updated = "now"
        elif today_in_tariff:
            last_updated = self.coordinator.last_updated.get("daily_peak")
        else:
            last_updated = self.coordinator.last_updated.get("monthly_peaks")
        return {
            "last_updated": last_updated,
        }


# ------------------------------------------------------------------
# Estimated cost increase
# ------------------------------------------------------------------

class PeakMonitorCostIncreaseSensor(PeakMonitorBaseSensor):
    """Sensor showing estimated monthly tariff cost increase.

    Shows how much the monthly tariff cost would increase if the current
    estimated hourly consumption becomes a new peak that displaces the
    current lowest monthly peak. Zero when the estimate would not affect
    the monthly average.
    """

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_COST_INCREASE}"
        self._attr_translation_key = "cost_increase_estimate"
        self._attr_native_unit_of_measurement = "SEK"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        # No device_class: this is a real-time delta (can be 0 or jump freely between hours).
        # MONETARY only allows total/total_increasing, neither of which applies here.
        self._attr_icon = "mdi:cash-plus"
        self._attr_suggested_display_precision = 2

    @property
    def available(self) -> bool:
        return self.coordinator.is_tariff_active()

    @property
    def native_value(self) -> float | None:
        return self.coordinator.get_estimated_cost_increase()



# ------------------------------------------------------------------
# Target consumption
# ------------------------------------------------------------------

class PeakMonitorTargetSensor(PeakMonitorBaseSensor):
    """Sensor showing the target consumption threshold."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_TARGET}"
        self._attr_translation_key = "target"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        # No device_class: these represent peak/threshold/estimation values in W,
        # not cumulative totals. ENERGY device_class requires total/total_increasing
        # which would be semantically wrong here. Unit display is unaffected.
        self._attr_icon = "mdi:target"
    
    def _update_unit_attributes(self) -> None:
        """Delegate to the shared base helper."""
        self._set_power_unit_attributes()

    @property
    def available(self) -> bool:
        return self.coordinator.is_tariff_active()

    @property
    def native_value(self) -> float:
        target_wh = self.coordinator.get_target_consumption()
        return round(self.coordinator._convert_to_output_unit(target_wh), 
                    self.coordinator.get_output_precision())

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "last_updated": self.coordinator.last_updated.get("target"),
        }


# ------------------------------------------------------------------
# Relative to target
# ------------------------------------------------------------------

class PeakMonitorRelativeSensor(PeakMonitorBaseSensor):
    """Sensor showing estimation relative to target (negative = under)."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_RELATIVE}"
        self._attr_translation_key = "relative_to_target"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        # No device_class: these represent peak/threshold/estimation values in W,
        # not cumulative totals. ENERGY device_class requires total/total_increasing
        # which would be semantically wrong here. Unit display is unaffected.
        self._attr_icon = "mdi:gauge"
    
    def _update_unit_attributes(self) -> None:
        """Delegate to the shared base helper."""
        self._set_power_unit_attributes()

    @property
    def available(self) -> bool:
        if not self.coordinator.is_tariff_active():
            return False
        if self.coordinator.cached_target == 0:
            return False
        # Also unavailable when the estimation is unreliable
        if not self.coordinator.estimation_sensor and self.coordinator._estimation_unreliable:
            return False
        return True

    @property
    def native_value(self) -> float | None:
        # Use the raw estimation (same value shown on the Current Hour Estimation sensor)
        # and the displayed target (same value shown on the Target sensor, already
        # scaled up by 1/reduced_factor during reduced hours). Both are in the same
        # display W space, so the difference is directly meaningful to the user.
        estimated = self.coordinator.get_estimated_consumption()
        if estimated is None:
            return None
        target = self.coordinator.get_target_consumption()
        relative_wh = estimated - target
        return round(self.coordinator._convert_to_output_unit(relative_wh),
                    self.coordinator.get_output_precision())



# ------------------------------------------------------------------
# Percentage of target
# ------------------------------------------------------------------

class PeakMonitorPercentageSensor(PeakMonitorBaseSensor):
    """Sensor showing estimation as percentage of target."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_PERCENTAGE}"
        self._attr_translation_key = "percentage_of_target"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:percent"
        self._attr_suggested_display_precision = 0

    @property
    def available(self) -> bool:
        if not self.coordinator.is_tariff_active():
            return False
        if self.coordinator.cached_target == 0:
            return False
        # Also unavailable when the estimation is unreliable
        if not self.coordinator.estimation_sensor and self.coordinator._estimation_unreliable:
            return False
        return True

    @property
    def native_value(self) -> int | None:
        # Same display-space calculation as the relative sensor: raw estimation
        # divided by the displayed target (already un-scaled in reduced mode).
        estimated = self.coordinator.get_estimated_consumption()
        if estimated is None:
            return None
        target = self.coordinator.get_target_consumption()
        if target == 0:
            return None
        return round((estimated / target) * 100)



# ------------------------------------------------------------------
# Internal estimation
# ------------------------------------------------------------------

class PeakMonitorInternalEstimationSensor(PeakMonitorBaseSensor):
    """Sensor showing internal estimation when no external sensor is configured."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_INTERNAL_ESTIMATION}"
        self._attr_translation_key = "interval_consumption_estimate"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        # No device_class: these represent peak/threshold/estimation values in W,
        # not cumulative totals. ENERGY device_class requires total/total_increasing
        # which would be semantically wrong here. Unit display is unaffected.
        self._attr_icon = "mdi:chart-line-variant"
    
    def _update_unit_attributes(self) -> None:
        """Delegate to the shared base helper."""
        self._set_power_unit_attributes()

    @property
    def available(self) -> bool:
        """Return True only when the consumption sensor is available, the tariff
        is active or reduced, and the estimation is reliable (sufficient data).
        During inactive periods the estimation is meaningless
        (the tariff is not running) so hide the sensor rather than show a stale value.
        During startup or after an hour boundary with no previous rate, hide the
        sensor until a reliable estimate can be produced."""
        return (
            self.coordinator.consumption_sensor_available
            and self.coordinator.is_tariff_active()
            and not self.coordinator._estimation_unreliable
        )

    @property
    def native_value(self) -> float | None:
        estimation = self.coordinator.get_internal_estimation()
        if estimation is None:
            return None
        return round(self.coordinator._convert_to_output_unit(estimation), 
                    self.coordinator.get_output_precision())



# ------------------------------------------------------------------
# Daily peak
# ------------------------------------------------------------------

class PeakMonitorDailyPeakSensor(PeakMonitorBaseSensor):
    """Sensor showing the current daily peak."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_DAILY_PEAK}"
        self._attr_translation_key = "daily_peak"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_icon = "mdi:chart-line"
    
    def _update_unit_attributes(self) -> None:
        """Delegate to the shared base helper."""
        self._set_power_unit_attributes()

    @property
    def available(self) -> bool:
        """Show the daily peak only once the tariff has been active or reduced today.

        At the very start of a new day the tariff is typically inactive (e.g. 00:00
        on a weekday with active hours starting at 06:00). During this window
        daily_peak holds the reset_value placeholder which would be misleading.
        Once the first active or reduced reading arrives the sensor stays visible
        for the rest of the day, including after a HA restart mid-day.
        """
        return self.coordinator.tariff_seen_active_today

    @property
    def native_value(self) -> float:
        return round(self.coordinator._convert_to_output_unit(self.coordinator.daily_peak), 
                    self.coordinator.get_output_precision())

    @property
    def extra_state_attributes(self) -> dict:
        # Report "now" when current estimated consumption already exceeds the committed
        # daily peak — the value is being influenced right now but not yet committed.
        if self.coordinator.is_daily_peak_affecting_now():
            last_updated = "now"
        else:
            last_updated = self.coordinator.last_updated.get("daily_peak")
        return {
            "last_updated": last_updated,
        }


# ------------------------------------------------------------------
# This hour's consumption (cumulative mode only)
# ------------------------------------------------------------------

class PeakMonitorHourConsumptionSensor(PeakMonitorBaseSensor):
    """Sensor showing this hour's consumption.

    Only created when the input sensor does NOT reset every hour (cumulative mode).
    Resets to 0 at every full hour automatically.
    """

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_HOUR_CONSUMPTION}"
        self._attr_translation_key = "interval_consumption"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_icon = "mdi:meter-electric"
    
    def _update_unit_attributes(self) -> None:
        """Delegate to the shared base helper."""
        self._set_power_unit_attributes()

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.has_received_reading:
            return None
        return round(self.coordinator._convert_to_output_unit(self.coordinator.hour_cumulative_consumption), 
                    self.coordinator.get_output_precision())


# ------------------------------------------------------------------
# Monthly peaks (individual)
# ------------------------------------------------------------------

class PeakMonitorMonthlyPeakSensor(PeakMonitorBaseSensor):
    """Sensor showing a single monthly peak value."""

    def __init__(
        self,
        coordinator: PeakMonitorCoordinator,
        entry: ConfigEntry,
        peak_index: int
    ) -> None:
        super().__init__(coordinator, entry)
        self.peak_index = peak_index
        self._attr_unique_id = f"{entry.entry_id}_monthly_peak_{peak_index + 1}"
        self._attr_translation_key = f"running_peak_{peak_index + 1}"
        self._attr_entity_registry_visible_default = False
        self._attr_entity_registry_enabled_default = False
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_icon = "mdi:podium"
    
    def _update_unit_attributes(self) -> None:
        """Delegate to the shared base helper."""
        self._set_power_unit_attributes()

    @property
    def native_value(self) -> float:
        if self.peak_index < len(self.coordinator.monthly_peaks):
            peak_wh = self.coordinator.monthly_peaks[self.peak_index]
            return round(self.coordinator._convert_to_output_unit(peak_wh), 
                        self.coordinator.get_output_precision())
        return 0

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "last_updated": self.coordinator.last_updated.get("monthly_peaks"),
        }


# ------------------------------------------------------------------
# Active state sensor (moved from binary_sensor)
# ------------------------------------------------------------------

class PeakMonitorActiveSensor(PeakMonitorBaseSensor):
    """Sensor showing the tariff state: Active, Reduced, or Inactive."""
    
    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_ACTIVE}"
        self._attr_translation_key = "status"
        self._attr_device_class = "enum"
        self._attr_options = StateMapper.get_state_options()
    
    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        internal_state = self.coordinator.get_tariff_active_state()
        return StateMapper.map_state(internal_state)
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return current state information (config moved to device info)."""
        import homeassistant.util.dt as dt_util
        now = dt_util.now()
        
        # Get state with reasons
        state, reasons = self.coordinator.get_tariff_active_state_with_reasons()

        attrs = {}
        
        # Add reason based on state
        # Priority order in reasons: Holiday > Weekend > Daily (time of day)
        if state == ACTIVE_STATE_OFF and reasons:
            # Inactive - show first reason (highest priority)
            attrs["inactive_reason"] = reasons[0]
        elif state == ACTIVE_STATE_REDUCED and reasons:
            # Reduced - show first reason (highest priority)
            attrs["reduced_reason"] = reasons[0]
        
        return attrs
    
    @property
    def icon(self) -> str:
        """Return icon and color based on state.
        
        Active: yellow circle
        Reduced: red circle  
        Inactive: grey circle outline
        """
        state = self.native_value
        if state == STATE_ACTIVE:
            return "mdi:circle"  # Will show in yellow with appropriate entity configuration
        elif state == STATE_REDUCED:
            return "mdi:circle"  # Will show in red
        else:  # inactive
            return "mdi:circle-outline"  # Grey outline
