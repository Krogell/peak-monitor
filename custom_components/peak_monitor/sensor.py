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
    SENSOR_IMMEDIATE_HEADROOM,
    SENSOR_RELATIVE,
    SENSOR_DAILY_PEAK,
    SENSOR_DAILY_SUB_PEAK,
    SENSOR_PERCENTAGE,
    SENSOR_COST,
    SENSOR_COST_INCREASE,
    SENSOR_INTERNAL_ESTIMATION,
    SENSOR_HOUR_CONSUMPTION,
    SENSOR_INTERVAL_CONSUMPTION,
    SENSOR_LINEAR_DEVIATION,
    SENSOR_SAFE_HEADROOM,
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
        # PeakMonitorLinearDeviationSensor — not published in this release
        PeakMonitorPercentageSensor(coordinator, entry),
        PeakMonitorActiveSensor(coordinator, entry),
    ]
    
    # Daily peak sensor - only in normal mode (only one peak per day)
    if coordinator.only_one_peak_per_day:
        entities.append(PeakMonitorDailyPeakSensor(coordinator, entry))

    # Daily sub-peak sensors — only when daily_peaks_averaged > 1
    if coordinator.only_one_peak_per_day and coordinator.daily_peaks_averaged > 1:
        for i in range(coordinator.daily_peaks_averaged):
            entities.append(PeakMonitorDailySubPeakSensor(coordinator, entry, i))
        # Immediate Headroom and Safe Headroom — only in averaging mode
        entities.append(PeakMonitorImmediateHeadroomSensor(coordinator, entry))
        entities.append(PeakMonitorSafeHeadroomSensor(coordinator, entry))

    # Cost sensors - only when price_per_kw is configured and > 0
    if coordinator.price_per_kw is not None and coordinator.price_per_kw > 0:
        entities.append(PeakMonitorCostSensor(coordinator, entry))
        entities.append(PeakMonitorCostIncreaseSensor(coordinator, entry))

    # Internal estimation sensor — only when no external sensor is configured
    if not coordinator.estimation_sensor:
        entities.append(PeakMonitorInternalEstimationSensor(coordinator, entry))

    # Hourly consumption sensor — when input is cumulative (non-resetting),
    # in multiple-peaks-per-day mode, or when using a power (W/kW) input sensor
    # (where hour_cumulative_consumption is the integrated Wh for the current hour).
    is_power_input = coordinator.input_unit in ("W", "kW")
    if not coordinator.sensor_resets_every_hour or not coordinator.only_one_peak_per_day or is_power_input:
        entities.append(PeakMonitorHourConsumptionSensor(coordinator, entry))

    # Individual monthly peak sensors
    for i in range(coordinator.number_of_peaks):
        entities.append(PeakMonitorMonthlyPeakSensor(coordinator, entry, i))

    async_add_entities(entities)


def _round_timestamp(dt):
    """Round a datetime to the nearest minute, stripping seconds.
    Returns None or string values unchanged."""
    if dt is None or isinstance(dt, str):
        return dt
    from datetime import timedelta
    seconds = (dt - dt.replace(second=0, microsecond=0)).total_seconds()
    if seconds >= 30:
        dt = dt + timedelta(minutes=1)
    return dt.replace(second=0, microsecond=0)


# ------------------------------------------------------------------
# Base class
# ------------------------------------------------------------------

class PeakMonitorBaseSensor(SensorEntity):
    """Base class for Peak Monitor sensors."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__()
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
        """Register coordinator callback and write initial state with attributes."""
        self.coordinator.add_listener(self._handle_coordinator_update)
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        self.coordinator.remove_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes, logging any exceptions for diagnostics."""
        try:
            return self._build_extra_attrs()
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Error building extra_state_attributes for %s (unique_id=%s)",
                self.__class__.__name__,
                getattr(self, "_attr_unique_id", "?"),
            )
            return {}

    def _build_extra_attrs(self) -> dict:
        """Override in subclasses to return extra attributes dict."""
        return {}

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
        self._attr_translation_key = "period_average"
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

    def _build_extra_attrs(self) -> dict:
        tariff_wh = self.coordinator.get_current_tariff(include_today=True)

        daily_peak = self.coordinator.daily_peak
        monthly_peaks = self.coordinator.monthly_peaks
        today_in_tariff = bool(monthly_peaks) and daily_peak > min(monthly_peaks)

        if today_in_tariff:
            commit_time = self.coordinator.last_updated.get("daily_peak")
        else:
            commit_time = self.coordinator.last_updated.get("monthly_peaks")

        attrs: dict = {
            "includes_today": today_in_tariff,
            "last_updated": _round_timestamp(commit_time),
        }

        # Only include price when a price is configured
        if self.coordinator.price_per_kw:
            price = self.coordinator.price_per_kw * tariff_wh / 1000
            attrs["price"] = round(price, 2)
            attrs["price_unit"] = self.coordinator.currency

        precision = self.coordinator.get_output_precision()

        if today_in_tariff:
            effective_peaks = sorted(monthly_peaks + [daily_peak], reverse=True)[:len(monthly_peaks)]
        else:
            effective_peaks = sorted(monthly_peaks, reverse=True)

        for i, peak in enumerate(effective_peaks, 1):
            converted_peak = self.coordinator._convert_to_output_unit(peak)
            is_today = today_in_tariff and abs(peak - daily_peak) < 0.01
            attrs[f"period_peak_{i}"] = round(converted_peak, precision)
            attrs[f"period_peak_{i}_is_today"] = is_today

        return attrs


# ------------------------------------------------------------------
# Monthly power grid fee
# ------------------------------------------------------------------

class PeakMonitorCostSensor(PeakMonitorBaseSensor):
    """Sensor showing the estimated monthly power grid fee."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_COST}"
        self._attr_translation_key = "period_cost"
        self._attr_native_unit_of_measurement = coordinator.currency
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

    def _build_extra_attrs(self) -> dict:
        today_in_tariff = self.coordinator.is_monthly_average_affecting_now()
        if today_in_tariff:
            commit_time = self.coordinator.last_updated.get("daily_peak")
        else:
            commit_time = self.coordinator.last_updated.get("monthly_peaks")
        return {
            "peak_last_updated": _round_timestamp(commit_time),
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
        self._attr_translation_key = "cost_increase_forecast"
        self._attr_native_unit_of_measurement = coordinator.currency
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

    def _build_extra_attrs(self) -> dict:
        precision = self.coordinator.get_output_precision()
        conv = self.coordinator._convert_to_output_unit
        attrs: dict = {}
        if self.coordinator.only_one_peak_per_day and self.coordinator.daily_peaks_averaged > 1:
            attrs["smallest_sub_peak"] = round(
                conv(min(self.coordinator.daily_sub_peaks)), precision
            )
        # Always expose the lowest period peak — useful for automations
        if self.coordinator.monthly_peaks:
            attrs["lowest_monthly_peak"] = round(
                conv(min(self.coordinator.monthly_peaks)), precision
            )
        return attrs


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

    def _build_extra_attrs(self) -> dict:
        return {
            "peak_last_updated": _round_timestamp(self.coordinator.last_updated.get("target")),
        }


# ------------------------------------------------------------------
# Immediate Headroom (averaging mode only)
# ------------------------------------------------------------------

class PeakMonitorImmediateHeadroomSensor(PeakMonitorBaseSensor):
    """Maximum consumption for this interval without increasing the monthly fee.

    Only created when daily_peaks_averaged > 1 (Jönköping averaging model).

    Headroom = N × lowest_monthly_peak − sum(top N-1 committed sub-peaks)
    Clamped below by the smallest committed sub-peak.

    This tells you the absolute ceiling for the current interval — if you stay
    below this value, your monthly average will not worsen.  Note that
    maximising this number every interval may fill up your sub-peak slots
    quickly and leave you with a worse position later in the day.
    """

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_IMMEDIATE_HEADROOM}"
        self._attr_translation_key = "immediate_headroom"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:speedometer"

    def _update_unit_attributes(self) -> None:
        self._set_power_unit_attributes()

    @property
    def available(self) -> bool:
        """Available under the same conditions as the Target sensor."""
        return self.coordinator.is_tariff_active()

    @property
    def native_value(self) -> float | None:
        headroom_wh = self.coordinator.get_immediate_headroom()
        if headroom_wh is None:
            return None
        if self.coordinator.get_tariff_active_state() == "reduced" and self.coordinator.reduced_factor > 0:
            # Scale up so the user sees the raw consumption limit (reduction applied on recording)
            headroom_wh = headroom_wh / self.coordinator.reduced_factor
        precision = self.coordinator.get_output_precision()
        return round(self.coordinator._convert_to_output_unit(headroom_wh), precision)

    def _build_extra_attrs(self) -> dict:
        n = self.coordinator.daily_peaks_averaged
        lowest_monthly = min(self.coordinator.monthly_peaks)
        sub = self.coordinator.daily_sub_peaks
        top_n_minus_1 = sorted(sub, reverse=True)[:n - 1]
        precision = self.coordinator.get_output_precision()
        conv = self.coordinator._convert_to_output_unit
        return {
            "n_sub_peaks": n,
            "lowest_monthly_peak": round(conv(lowest_monthly), precision),
            "sub_peaks": [round(conv(s), precision) for s in sorted(sub, reverse=True)],
            "top_n_minus_1_sum": round(conv(sum(top_n_minus_1)), precision),
        }



# ------------------------------------------------------------------
# Safe Headroom (averaging mode only)
# ------------------------------------------------------------------

class PeakMonitorSafeHeadroomSensor(PeakMonitorBaseSensor):
    """Consumption level that cannot worsen the rest-of-day position.

    Only created when daily_peaks_averaged > 1 (Jönköping averaging model).

    Safe Headroom = min(committed sub-peaks): as long as every remaining
    interval stays below this value, no sub-peak slot can worsen — the top-N
    average is guaranteed not to increase.

    Unlike Immediate Headroom (the ceiling before the monthly fee worsens),
    Safe Headroom is a guaranteed-safe floor useful for advanced automation
    strategies that need a risk-free operating point throughout the day.
    """

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_SAFE_HEADROOM}"
        self._attr_translation_key = "safe_headroom"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:shield-check"

    def _update_unit_attributes(self) -> None:
        self._set_power_unit_attributes()

    @property
    def available(self) -> bool:
        """Available under the same conditions as Immediate Headroom."""
        return self.coordinator.is_tariff_active()

    @property
    def native_value(self) -> float | None:
        safe_wh = self.coordinator.get_safe_headroom()
        if safe_wh is None:
            return None
        if self.coordinator.get_tariff_active_state() == "reduced" and self.coordinator.reduced_factor > 0:
            safe_wh = safe_wh / self.coordinator.reduced_factor
        return round(self.coordinator._convert_to_output_unit(safe_wh),
                     self.coordinator.get_output_precision())

    def _build_extra_attrs(self) -> dict:
        sub = self.coordinator.daily_sub_peaks
        precision = self.coordinator.get_output_precision()
        conv = self.coordinator._convert_to_output_unit
        n = self.coordinator.daily_peaks_averaged
        return {
            "n_sub_peaks": n,
            "sub_peaks": [round(conv(s), precision) for s in sorted(sub, reverse=True)],
            "smallest_sub_peak": round(conv(min(sub)), precision) if sub else None,
        }


# ------------------------------------------------------------------
# Relative to target
# ------------------------------------------------------------------

class PeakMonitorRelativeSensor(PeakMonitorBaseSensor):
    """Sensor showing how much headroom remains below target (positive = under, negative = over)."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_RELATIVE}"
        self._attr_translation_key = "target_headroom"
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
        if not self.coordinator.consumption_sensor_available:
            return False
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
        headroom_wh = target - estimated
        return round(self.coordinator._convert_to_output_unit(headroom_wh),
                    self.coordinator.get_output_precision())

    def _build_extra_attrs(self) -> dict:
        precision = self.coordinator.get_output_precision()
        estimated = self.coordinator.get_estimated_consumption()
        target = self.coordinator.get_target_consumption()
        attrs = {}
        if estimated is not None:
            attrs["estimated"] = round(self.coordinator._convert_to_output_unit(estimated), precision)
        if target:
            attrs["target"] = round(self.coordinator._convert_to_output_unit(target), precision)
        return attrs


# ------------------------------------------------------------------
# Linear deviation from ideal pace
# ------------------------------------------------------------------

class PeakMonitorLinearDeviationSensor(PeakMonitorBaseSensor):
    """Sensor showing how far actual consumption deviates from ideal linear pace.

    The ideal model assumes perfectly even consumption across the interval.
    At any moment the "ideal so far" is: target × (elapsed / interval_duration).

    Positive value → consuming faster than ideal pace (risk of exceeding target).
    Negative value → consuming slower than ideal pace (room to spare).

    Only available when the target is active and a reading has been received.
    """

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_LINEAR_DEVIATION}"
        self._attr_translation_key = "consumption_pace_deviation"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_registry_enabled_default = False
        # No device_class: deviation can be positive or negative (MEASUREMENT),
        # and SensorDeviceClass.ENERGY requires total/total_increasing state class
        # which HA enforces strictly and would break platform setup.
        self._attr_icon = "mdi:chart-timeline-variant-shimmer"

    def _update_unit_attributes(self) -> None:
        """Set energy unit (Wh or kWh) to match the coordinator output unit."""
        ou = self.coordinator.output_unit
        if ou == "kW":
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_suggested_display_precision = 3
        else:
            self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
            self._attr_suggested_display_precision = 1

    @property
    def available(self) -> bool:
        if not self.coordinator.consumption_sensor_available:
            return False
        if not self.coordinator.is_tariff_active():
            return False
        if self.coordinator.cached_target == 0:
            return False
        return True

    def _to_energy_unit(self, wh: float) -> float:
        """Convert Wh to display energy unit (kWh when output unit is kW)."""
        return wh / 1000.0 if self.coordinator.output_unit == "kW" else wh

    @property
    def native_value(self) -> float | None:
        deviation_wh = self.coordinator.get_linear_deviation()
        if deviation_wh is None:
            return None
        precision = 3 if self.coordinator.output_unit == "kW" else 1
        return round(self._to_energy_unit(deviation_wh), precision)

    def _build_extra_attrs(self) -> dict:
        target = self.coordinator.get_target_consumption()
        deviation_wh = self.coordinator.get_linear_deviation()
        precision = 3 if self.coordinator.output_unit == "kW" else 1
        attrs: dict = {}
        if target:
            attrs["target"] = round(self._to_energy_unit(target), precision)
        if deviation_wh is not None:
            actual = self.coordinator.hour_cumulative_consumption
            ideal = actual - deviation_wh
            attrs["actual_so_far"] = round(self._to_energy_unit(actual), precision)
            attrs["ideal_so_far"] = round(self._to_energy_unit(ideal), precision)
        return attrs


# ------------------------------------------------------------------
# Percentage of target
# ------------------------------------------------------------------

class PeakMonitorPercentageSensor(PeakMonitorBaseSensor):
    """Sensor showing estimation as percentage of target."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_PERCENTAGE}"
        self._attr_translation_key = "target_usage_percentage"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:percent"
        self._attr_suggested_display_precision = 0
        self._attr_entity_registry_enabled_default = False

    @property
    def available(self) -> bool:
        if not self.coordinator.consumption_sensor_available:
            return False
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

    def _build_extra_attrs(self) -> dict:
        precision = self.coordinator.get_output_precision()
        estimated = self.coordinator.get_estimated_consumption()
        target = self.coordinator.get_target_consumption()
        attrs = {}
        if estimated is not None:
            attrs["estimated"] = round(self.coordinator._convert_to_output_unit(estimated), precision)
        if target:
            attrs["target"] = round(self.coordinator._convert_to_output_unit(target), precision)
        return attrs


# ------------------------------------------------------------------
# Internal estimation
# ------------------------------------------------------------------

class PeakMonitorInternalEstimationSensor(PeakMonitorBaseSensor):
    """Sensor showing internal estimation when no external sensor is configured."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_INTERNAL_ESTIMATION}"
        self._attr_translation_key = "interval_consumption_forecast"
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

    def _build_extra_attrs(self) -> dict:
        precision = self.coordinator.get_output_precision()
        target = self.coordinator.get_target_consumption()
        attrs = {}
        if target:
            attrs["target"] = round(self.coordinator._convert_to_output_unit(target), precision)
        return attrs


# ------------------------------------------------------------------
# Daily peak
# ------------------------------------------------------------------

class PeakMonitorDailyPeakSensor(PeakMonitorBaseSensor):
    """Sensor showing the current daily peak."""

    def __init__(self, coordinator: PeakMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_DAILY_PEAK}"
        self._attr_translation_key = (
            "daily_peak_average"
            if coordinator.only_one_peak_per_day and coordinator.daily_peaks_averaged > 1
            else "daily_peak"
        )
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_icon = "mdi:chart-line"
        self._attr_entity_registry_enabled_default = True
    
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
        live = self.coordinator.get_live_daily_peak()
        return round(self.coordinator._convert_to_output_unit(live),
                    self.coordinator.get_output_precision())

    def _build_extra_attrs(self) -> dict:
        # Report "now" when current estimated consumption already exceeds the committed
        # daily peak — the value is being influenced right now but not yet committed.
        attrs: dict = {"peak_last_updated": _round_timestamp(
            self.coordinator.last_updated.get("daily_peak")
        )}

        # When daily_peaks_averaged > 1, expose committed sub-peak details
        if self.coordinator.daily_peaks_averaged > 1:
            attrs["averaging_model"] = f"avg of {self.coordinator.daily_peaks_averaged} highest peaks per day"
            precision = self.coordinator.get_output_precision()
            for i, sp in enumerate(self.coordinator.daily_sub_peaks, 1):
                attrs[f"committed_sub_peak_{i}"] = round(
                    self.coordinator._convert_to_output_unit(sp), precision
                )

        return attrs


# ------------------------------------------------------------------
# Daily sub-peaks (individual, only when daily_peaks_averaged > 1)
# ------------------------------------------------------------------

class PeakMonitorDailySubPeakSensor(PeakMonitorBaseSensor):
    """Sensor showing one intra-day sub-peak used for daily averaging.

    Created only when daily_peaks_averaged > 1.  These sensors expose the
    individual readings that are averaged to produce the daily committed value.
    Hidden in the entity registry by default; useful for dashboards and automations.
    """

    def __init__(
        self,
        coordinator: PeakMonitorCoordinator,
        entry: ConfigEntry,
        sub_peak_index: int,
    ) -> None:
        super().__init__(coordinator, entry)
        self.sub_peak_index = sub_peak_index
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_DAILY_SUB_PEAK}_{sub_peak_index + 1}"
        self._attr_translation_key = f"daily_sub_peak_{sub_peak_index + 1}"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_icon = "mdi:chart-bar"
        self._attr_entity_registry_enabled_default = False

    def _update_unit_attributes(self) -> None:
        self._set_power_unit_attributes()

    @property
    def available(self) -> bool:
        """Visible once the tariff has been active today."""
        return self.coordinator.tariff_seen_active_today

    @property
    def native_value(self) -> float:
        if self.sub_peak_index < len(self.coordinator.daily_sub_peaks):
            sp = self.coordinator.daily_sub_peaks[self.sub_peak_index]
            return round(
                self.coordinator._convert_to_output_unit(sp),
                self.coordinator.get_output_precision(),
            )
        return 0

    def _build_extra_attrs(self) -> dict:
        return {
            "peak_last_updated": _round_timestamp(self.coordinator.last_updated.get("daily_sub_peaks")),
            "rank": self.sub_peak_index + 1,
        }


# ------------------------------------------------------------------
# This hour's consumption (cumulative mode only)
# ------------------------------------------------------------------

class PeakMonitorHourConsumptionSensor(PeakMonitorBaseSensor):
    """Sensor showing this hour's accumulated consumption.

    Created when the input sensor is cumulative (non-resetting), when using
    a power (W/kW) input sensor (showing integrated Wh for the current hour),
    or in multiple-peaks-per-day mode.
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
    def available(self) -> bool:
        return self.coordinator.consumption_sensor_available

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.has_received_reading:
            return None
        return round(self.coordinator._convert_to_output_unit(self.coordinator.hour_cumulative_consumption), 
                    self.coordinator.get_output_precision())

    def _build_extra_attrs(self) -> dict:
        precision = self.coordinator.get_output_precision()
        target = self.coordinator.get_target_consumption()
        attrs = {}
        if target:
            attrs["target"] = round(self.coordinator._convert_to_output_unit(target), precision)
        return attrs


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
        self._attr_unique_id = f"{entry.entry_id}_period_peak_{peak_index + 1}"
        self._attr_translation_key = f"period_peak_{peak_index + 1}"
        self._update_unit_attributes()
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_icon = "mdi:podium"
        self._attr_entity_registry_enabled_default = False
    
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

    def _build_extra_attrs(self) -> dict:
        return {
            "peak_last_updated": _round_timestamp(self.coordinator.last_updated.get("monthly_peaks")),
        }


# ------------------------------------------------------------------
# Active state sensor
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
    
    def _build_extra_attrs(self) -> dict:
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
