"""The Peak Monitor integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_point_in_time,
)
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from .const import (
    ACTIVE_STATE_OFF,
    ACTIVE_STATE_ON,
    ACTIVE_STATE_REDUCED,
    DEFAULT_ACTIVE_END_HOUR,
    DEFAULT_ACTIVE_START_HOUR,
    DEFAULT_CURRENCY,
    DEFAULT_DAILY_PEAKS_AVERAGED,
    DEFAULT_FIXED_MONTHLY_FEE,
    DEFAULT_ONLY_ONE_PEAK_PER_DAY,
    DEFAULT_NUMBER_OF_PEAKS,
    DEFAULT_PRICE_PER_KW,
    DEFAULT_REDUCED_ALSO_ON_WEEKENDS,
    DEFAULT_REDUCED_END_HOUR,
    DEFAULT_REDUCED_FACTOR,
    DEFAULT_REDUCED_START_HOUR,
    DEFAULT_RESET_INTERVAL,
    DEFAULT_RESET_VALUE,
    DEFAULT_INTERVAL_MINUTES,
    DEFAULT_SENSOR_RESETS_EVERY_HOUR,
    DEFAULT_WEEKEND_START_HOUR,
    DEFAULT_WEEKEND_END_HOUR,
    REASON_EXTERNAL_MUTE,
    REASON_EXCLUDED_MONTH,
    REASON_HOLIDAY,
    REASON_WEEKEND,
    REASON_TIME_OF_DAY,
    REASON_EXTERNAL_CONTROL,
    BEHAVIOR_NO_TARIFF,
    BEHAVIOR_REDUCED_TARIFF,
    HOLIDAY_OFFICIAL,
    RESET_INTERVAL_WEEKLY,
    RESET_INTERVAL_MONTHLY,
    RESET_INTERVAL_MANUAL,
    SERVICE_RESET_PEAK,
)
from .utils import (
    calculate_internal_estimation,
    check_input_sensor_unit,
    get_bool,
    get_consumption_with_reduction,
    get_float,
    get_int,
    get_list,
    get_str,
    is_time_in_range,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "peak_monitor"
PLATFORMS = [Platform.SENSOR]

STORAGE_VERSION = 1
STORAGE_KEY = "peak_monitor_data"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Peak Monitor from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = PeakMonitorCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register services (once, idempotent)
    _register_services(hass)

    # Fire any configuration warnings as persistent notifications
    await _async_fire_config_warnings(hass, entry, coordinator)

    return True


async def _async_fire_config_warnings(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: "PeakMonitorCoordinator",
) -> None:
    """Fire persistent notifications for runtime configuration issues.

    Only fires unit-mismatch warnings — these are runtime checks because the
    consumption sensor's reported unit can change independently of the integration
    config. Warnings about incompatible config choices (averaging + multiple peaks,
    sub-hour intervals) are shown once in the config/reconfig flow instead.

    To avoid re-appearing on every HA restart, each notification is only created
    if it does not already exist (i.e. has not been dismissed by the user).
    """
    from homeassistant.components.persistent_notification import async_create

    data = {**entry.data, **entry.options}
    instance = data.get("name", "Peak Monitor")
    id_prefix = f"peak_monitor_{entry.entry_id}"

    def _notification_exists(notification_id: str) -> bool:
        """Return True if the notification is currently shown (not dismissed)."""
        return hass.states.get(f"persistent_notification.{notification_id}") is not None

    # ----------------------------------------------------------------
    # 1. Input unit: compare configured vs sensor-reported unit
    # ----------------------------------------------------------------
    _HA_UNIT_MAP = {
        "kWh": "kWh", "kilowatt_hour": "kWh",
        "kW": "kW",   "kilowatt": "kW",
        "Wh": "Wh",   "watt_hour": "Wh",
        "W": "W",     "watt": "W",
    }
    consumption_sensor = data.get("consumption_sensor")
    sensor_state = hass.states.get(consumption_sensor) if consumption_sensor else None
    sensor_unit_raw = sensor_state.attributes.get("unit_of_measurement", "") if sensor_state else ""
    detected_unit = _HA_UNIT_MAP.get(sensor_unit_raw)
    _cfg_unit_raw = data.get("input_unit", "")
    configured_unit = "" if _cfg_unit_raw in ("auto", "", None) else _cfg_unit_raw  # "" = auto

    conflict_id = f"{id_prefix}_unit_conflict"
    unknown_id = f"{id_prefix}_unit_unknown"

    if detected_unit and configured_unit and configured_unit != detected_unit:
        if not _notification_exists(conflict_id):
            async_create(
                hass,
                title=f"⚠️ Peak Monitor — Unit conflict ({instance})",
                message=(
                    f"The **Input Unit** in the advanced settings is set to **{configured_unit}**, "
                    f"but your sensor `{consumption_sensor}` reports **{sensor_unit_raw}**.\n\n"
                    f"**What happens:** Auto-detection overrides the manual setting. "
                    f"Peak Monitor will treat readings as **{detected_unit}**.\n\n"
                    f"To silence this warning, either set Input Unit to *Auto* (recommended) "
                    f"or change it to match your sensor's unit."
                ),
                notification_id=conflict_id,
            )
        _LOGGER.warning(
            "Peak Monitor (%s): input unit conflict — configured=%s, sensor reports=%s, using %s",
            instance, configured_unit, sensor_unit_raw, detected_unit,
        )

    elif not detected_unit and not configured_unit:
        if not _notification_exists(unknown_id):
            async_create(
                hass,
                title=f"⚠️ Peak Monitor — Unit unknown ({instance})",
                message=(
                    f"Your sensor `{consumption_sensor}` has no `unit_of_measurement` attribute "
                    f"and no manual **Input Unit** has been configured.\n\n"
                    f"**What happens:** Peak Monitor will assume readings are in **Wh** (watt-hours). "
                    f"If your sensor uses a different unit this will cause incorrect peak values.\n\n"
                    f"To fix this, open the integration settings → Advanced → Input Unit and select "
                    f"the correct unit for your sensor."
                ),
                notification_id=unknown_id,
            )
        _LOGGER.warning(
            "Peak Monitor (%s): no unit detected and no manual unit configured — assuming Wh",
            instance,
        )


def _register_services(hass: HomeAssistant) -> None:
    """Register Peak Monitor services (safe to call multiple times)."""
    import voluptuous as vol

    if hass.services.has_service(DOMAIN, SERVICE_RESET_PEAK):
        return

    async def handle_reset_peak(call) -> None:
        """Handle the reset_peak service call.

        peak_index meaning:
          Omitted / None  — reset ALL monthly peaks AND daily peak
          0               — reset only the daily peak (and daily_sub_peaks)
          1..N            — reset that monthly peak slot (1-based)
        """
        peak_index = call.data.get("peak_index")    # None, 0, or 1-based monthly index
        reset_to = call.data.get("reset_value")     # optional override
        target_entry_id = call.data.get("config_entry_id")  # optional — None = all instances

        all_coordinators = hass.data.get(DOMAIN, {})

        # Filter to the requested instance (or all if not specified)
        if target_entry_id:
            if target_entry_id not in all_coordinators:
                _LOGGER.warning(
                    "reset_peak: config_entry_id '%s' not found. Available: %s",
                    target_entry_id, list(all_coordinators.keys()),
                )
                return
            coordinators = {target_entry_id: all_coordinators[target_entry_id]}
        else:
            coordinators = all_coordinators

        for entry_id, coordinator in coordinators.items():
            base_reset = coordinator.reset_value if reset_to is None else float(reset_to)

            reset_daily = False
            monthly_indices = []

            if peak_index is None:
                # Reset everything: all monthly peaks AND daily peak
                monthly_indices = list(range(len(coordinator.monthly_peaks)))
                reset_daily = True
            elif int(peak_index) == 0:
                # Index 0 = daily peak only
                reset_daily = True
            else:
                # 1-based monthly index
                idx = int(peak_index) - 1
                if idx < 0 or idx >= len(coordinator.monthly_peaks):
                    _LOGGER.warning(
                        "reset_peak: peak_index %s out of range (1-%s) for entry %s",
                        peak_index, len(coordinator.monthly_peaks), entry_id,
                    )
                    continue
                monthly_indices = [idx]

            # Reset monthly peak slots
            for i in monthly_indices:
                current = coordinator.monthly_peaks[i]
                effective_reset = min(base_reset, current)
                if base_reset > current:
                    from homeassistant.components.persistent_notification import async_create
                    instance = coordinator.entry.data.get("name", "Peak Monitor")
                    async_create(
                        hass,
                        title=f"Peak Monitor — Reset ignored ({instance})",
                        message=(
                            f"You tried to reset monthly peak slot {i + 1} to "
                            f"**{base_reset:.0f}**, but the current value is "
                            f"**{current:.0f}**.\n\n"
                            f"Resetting a peak to a **higher** value is not allowed — "
                            f"it would artificially inflate your period average and "
                            f"give a false picture of your tariff position.\n\n"
                            f"**The reset was disregarded.** The peak remains at "
                            f"{current:.0f}. To lower the peak, set the reset value "
                            f"to a number equal to or below the current value."
                        ),
                        notification_id=f"peak_monitor_{entry_id}_reset_too_high_{i}",
                    )
                    _LOGGER.warning(
                        "reset_peak: reset_value %s > current peak %s for slot %s "
                        "in entry %s — reset disregarded",
                        base_reset, current, i + 1, entry_id,
                    )
                    continue
                coordinator.monthly_peaks[i] = effective_reset

            # Reset daily peak (and sub-peaks if in averaging mode)
            if reset_daily:
                current_daily = coordinator.daily_peak
                if base_reset > current_daily:
                    from homeassistant.components.persistent_notification import async_create
                    instance = coordinator.entry.data.get("name", "Peak Monitor")
                    async_create(
                        hass,
                        title=f"Peak Monitor — Daily reset ignored ({instance})",
                        message=(
                            f"You tried to reset the daily peak to "
                            f"**{base_reset:.0f}**, but the current daily peak is "
                            f"**{current_daily:.0f}**.\n\n"
                            f"Resetting a peak to a **higher** value is not allowed. "
                            f"**The reset was disregarded.** Set the reset value to "
                            f"{current_daily:.0f} or below to perform a valid reset."
                        ),
                        notification_id=f"peak_monitor_{entry_id}_daily_reset_too_high",
                    )
                    _LOGGER.warning(
                        "reset_peak: reset_value %s > daily_peak %s for entry %s "
                        "— daily reset disregarded",
                        base_reset, current_daily, entry_id,
                    )
                else:
                    effective_daily_reset = base_reset
                    coordinator.daily_peak = effective_daily_reset
                    coordinator.daily_sub_peaks = [effective_daily_reset] * coordinator.daily_peaks_averaged
                    coordinator.tariff_seen_active_today = coordinator.daily_peak > coordinator.reset_value
                    coordinator.last_updated["daily_peak"] = dt_util.now()
                    coordinator.last_updated["daily_sub_peaks"] = dt_util.now()
                    _LOGGER.info(
                        "reset_peak service: daily peak reset to %s Wh for entry %s",
                        effective_daily_reset, entry_id,
                    )

            # Recalculate target and notify
            coordinator._force_update_target()
            await coordinator._async_save_data()
            await coordinator._async_notify_listeners()
            _LOGGER.info(
                "reset_peak service: monthly indices %s, daily=%s for entry %s. "
                "Monthly peaks now: %s",
                [i + 1 for i in monthly_indices], reset_daily, entry_id,
                coordinator.monthly_peaks,
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_PEAK,
        handle_reset_peak,
        schema=vol.Schema({
            vol.Optional("config_entry_id"): str,
            vol.Optional("peak_index"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
            vol.Optional("reset_value"): vol.All(vol.Coerce(float), vol.Range(min=0)),
        }),
    )


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when it changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok


class PeakMonitorCoordinator:
    """Coordinator to manage peak monitor state and calculations."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")

        # Load configuration
        self._load_config(entry)

        # State
        self.daily_peak = self.reset_value
        self.monthly_peaks = [self.reset_value] * self.number_of_peaks
        self.last_month = None
        self.last_day = None

        # Intra-day sub-peaks — used when daily_peaks_averaged > 1.
        # Tracks the top N readings within the current day; their average is
        # the value committed to monthly_peaks at midnight.
        # Length == daily_peaks_averaged; all initialised to reset_value.
        self.daily_sub_peaks: list[float] = [self.reset_value] * self.daily_peaks_averaged

        # Cumulative sensor tracking (only active when sensor_resets_every_hour is False)
        self.last_cumulative_value: float | None = None
        self.last_seen_cumulative_value: float | None = None

        # Power sensor integration tracking (for W/kW input mode)
        # Stores (timestamp, power_watts) of the last received reading
        self._last_power_sample: tuple[datetime, float] | None = None
        # Accumulated Wh for current hour from power integration
        self._power_integrated_wh: float = 0.0

        # When True, the next cumulative reading after a restart re-baselines
        # so hour_cumulative_consumption starts from 0.  Only applies when the
        # consumption sensor IS present (if missing, the stored reading is kept).
        self._restart_rebaseline_needed: bool = False

        # Sensor availability tracking
        self.consumption_sensor_available = True

        # Internal estimation tracking
        self.consumption_samples: list[tuple[datetime, float]] = []
        self.hour_cumulative_consumption = 0.0
        # Rate (Wh/s) observed at end of previous hour — used as fallback
        # so the estimation sensor doesn't show 0 for the first minutes.
        self.previous_hour_rate: float | None = None

        # True while we lack sufficient samples for a reliable estimation.
        # When True the estimation sensor (and dependents) report unavailable.
        self._estimation_unreliable: bool = True

        # Cached target
        self.cached_target = self.reset_value
        self.last_target_update_hour: int | None = None

        # Flag: True once the first real sensor reading has been processed
        # Used to show unavailable instead of 0 on startup
        self.has_received_reading: bool = False

        # Flag: True once the tariff has been active or reduced at any point today.
        # Used to keep the daily peak sensor visible once it has first shown a value,
        # while hiding it at the very start of a day when the tariff is still inactive.
        self.tariff_seen_active_today: bool = False

        # Last-updated timestamps — recorded whenever a value changes
        self.last_updated: dict = {
            "daily_peak": None,
            "daily_sub_peaks": None,
            "monthly_peaks": None,
            "hour_consumption": None,
            "state": None,
            "target": None,
        }

        # Callbacks
        self._unsub_hourly = None
        self._unsub_daily = None
        self._unsub_estimation = None
        self._unsub_consumption = None
        self._listeners: list = []

        # Lock to serialise consumption events and prevent race conditions
        # when the input sensor fires multiple updates in rapid succession.
        self._processing_lock = asyncio.Lock()

        # Flag: unit warning has been issued for the input sensor (once only)
        self._input_unit_warned: bool = False

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _load_config(self, config_entry: ConfigEntry) -> None:
        """Load configuration from config entry (data + options)."""
        data = {**config_entry.data, **config_entry.options}

        self.consumption_sensor = data["consumption_sensor"]
        # Normalize estimation_sensor: convert empty string, "None" string, or None to actual None
        estimation_sensor_raw = data.get("estimation_sensor")
        if estimation_sensor_raw:
            est_str = str(estimation_sensor_raw).strip()
            self.estimation_sensor = None if (not est_str or est_str.lower() == "none") else estimation_sensor_raw
        else:
            self.estimation_sensor = None
        self.price_per_kw = get_float(data, "price_per_kw", DEFAULT_PRICE_PER_KW)
        self.fixed_monthly_fee = get_float(data, "fixed_monthly_fee", DEFAULT_FIXED_MONTHLY_FEE)
        self.active_start_hour = get_int(data, "active_start_hour", DEFAULT_ACTIVE_START_HOUR)
        self.active_end_hour = get_int(data, "active_end_hour", DEFAULT_ACTIVE_END_HOUR)

        active_months_raw = data.get("active_months", ["11", "12", "1", "2", "3"])
        self.active_months = [int(m) for m in active_months_raw]

        self.number_of_peaks = get_int(data, "number_of_peaks", DEFAULT_NUMBER_OF_PEAKS)

        # Holiday configuration
        from .const import (
            OFFICIAL_HOLIDAYS,
            DEFAULT_HOLIDAYS,
            HOLIDAY_OFFICIAL,
            HOLIDAY_EPIPHANY_EVE,
            HOLIDAY_EASTER_EVE,
            HOLIDAY_MIDSUMMER_EVE,
            HOLIDAY_CHRISTMAS_EVE,
            HOLIDAY_NEW_YEARS_EVE,
        )
        
        holidays_config = data.get("holidays", DEFAULT_HOLIDAYS)
        self.exclude_holidays = []
        self.exclude_holiday_evenings = []
        
        for item in holidays_config:
            if item == HOLIDAY_OFFICIAL:
                self.exclude_holidays.extend(OFFICIAL_HOLIDAYS)
            elif item in [HOLIDAY_EPIPHANY_EVE, HOLIDAY_EASTER_EVE, HOLIDAY_MIDSUMMER_EVE, 
                         HOLIDAY_CHRISTMAS_EVE, HOLIDAY_NEW_YEARS_EVE]:
                self.exclude_holiday_evenings.append(item)
            else:
                self.exclude_holidays.append(item)

        self.holiday_behavior = data.get("holiday_behavior", "no_tariff")
        self.weekend_behavior = data.get("weekend_behavior", "no_tariff")
        self.weekend_start_hour = get_int(data, "weekend_start_hour", DEFAULT_WEEKEND_START_HOUR)
        self.weekend_end_hour = get_int(data, "weekend_end_hour", DEFAULT_WEEKEND_END_HOUR)
        
        # External mute sensor - optional binary sensor to override and mute tariff
        external_mute_raw = data.get("external_mute_sensor")
        if external_mute_raw:
            ext_str = str(external_mute_raw).strip()
            self.external_mute_sensor = None if (not ext_str or ext_str.lower() == "none") else external_mute_raw
        else:
            self.external_mute_sensor = None
        
        # External reduced tariff sensor - optional binary sensor to activate reduced tariff
        external_reduced_raw = data.get("external_reduced_sensor")
        if external_reduced_raw:
            ext_str = str(external_reduced_raw).strip()
            self.external_reduced_sensor = None if (not ext_str or ext_str.lower() == "none") else external_reduced_raw
        else:
            self.external_reduced_sensor = None

        self.reset_value = get_int(data, "reset_value", DEFAULT_RESET_VALUE)

        # Reset interval: weekly, monthly (default), or manual
        self.reset_interval = data.get("reset_interval", DEFAULT_RESET_INTERVAL)
        self.interval_minutes: int = int(data.get("interval_minutes", DEFAULT_INTERVAL_MINUTES))

        # Currency for cost display (ISO 4217, default SEK)
        self.currency = data.get("currency", DEFAULT_CURRENCY)

        # Input unit — convert kWh/kW input to Wh internally
        # W/kW inputs are power sensors — integration is calculated
        _raw_input_unit = data.get("input_unit", "Wh")
        # Normalise "auto" or "" (legacy sentinel) to the fallback "Wh";
        # in normal flow validate_input already resolves these to a real unit.
        self.input_unit = _raw_input_unit if _raw_input_unit not in ("auto", "", None) else "Wh"
        
        # Output unit — display sensors in W or kW
        self.output_unit = data.get("output_unit", "W")

        # Whether the consumption sensor resets every hour (True) or is
        # cumulative / ever-increasing (False).
        self.sensor_resets_every_hour = get_bool(data, "sensor_resets_every_hour", DEFAULT_SENSOR_RESETS_EVERY_HOUR)

        # Only one peak per day mode (inverted: True = normal mode, False = multiple peaks mode)
        self.only_one_peak_per_day = get_bool(data, "only_one_peak_per_day", DEFAULT_ONLY_ONE_PEAK_PER_DAY)

        # How many intra-day peaks to average for the daily committed value.
        # 1 = disabled (standard single-peak behaviour).
        # > 1 = enabled only when only_one_peak_per_day is True; otherwise ignored.
        self.daily_peaks_averaged = get_int(data, "daily_peaks_averaged", DEFAULT_DAILY_PEAKS_AVERAGED)
        # Clamp to a safe range; guard against bad config values
        self.daily_peaks_averaged = max(1, min(self.daily_peaks_averaged, 10))

        self.reduced_tariff_enabled = data.get("daily_reduced_tariff_enabled", 
                                               data.get("reduced_tariff_enabled", False))
        self.reduced_start_hour = get_int(data, "reduced_start_hour", DEFAULT_REDUCED_START_HOUR)
        self.reduced_end_hour = get_int(data, "reduced_end_hour", DEFAULT_REDUCED_END_HOUR)
        self.reduced_factor = get_float(data, "reduced_factor", DEFAULT_REDUCED_FACTOR)
        self.reduced_also_on_weekends = data.get("reduced_also_on_weekends", DEFAULT_REDUCED_ALSO_ON_WEEKENDS)

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Set up the coordinator."""
        # Load stored data
        stored_data = await self.store.async_load()
        if stored_data:
            # Detect if the consumption sensor was changed since last run.
            # If so, discard all per-sensor accumulator state (cumulative baseline,
            # interval accumulator, power samples) — readings from the old sensor
            # are not comparable to the new sensor and would cause wrong peaks.
            stored_sensor = stored_data.get("consumption_sensor")
            sensor_changed = (
                stored_sensor is not None
                and stored_sensor != self.consumption_sensor
            )
            if sensor_changed:
                _LOGGER.warning(
                    "Peak Monitor: consumption sensor changed from '%s' to '%s'. "
                    "Discarding per-sensor accumulator state (interval consumption, "
                    "cumulative baseline). Peak and monthly data are preserved.",
                    stored_sensor, self.consumption_sensor,
                )

            self.daily_peak = stored_data.get("daily_peak", self.reset_value)
            self.monthly_peaks = stored_data.get("monthly_peaks",
                                                 [self.reset_value] * self.number_of_peaks)
            self.last_month = stored_data.get("last_month")
            self.last_day = stored_data.get("last_day")
            # Only restore cumulative baseline if the sensor hasn't changed
            self.last_cumulative_value = (
                None if sensor_changed
                else stored_data.get("last_cumulative_value")
            )

            # Restore daily_sub_peaks if present; resize if daily_peaks_averaged changed
            stored_sub = stored_data.get("daily_sub_peaks")
            if stored_sub is not None:
                n = self.daily_peaks_averaged
                if len(stored_sub) == n:
                    self.daily_sub_peaks = stored_sub
                elif len(stored_sub) > n:
                    self.daily_sub_peaks = sorted(stored_sub, reverse=True)[:n]
                else:
                    # Grew — pad with reset_value
                    self.daily_sub_peaks = stored_sub + [self.reset_value] * (n - len(stored_sub))

            # Restore last_updated timestamps (stored as unix timestamps)
            for key in ("daily_peak", "daily_sub_peaks", "monthly_peaks", "target"):
                stored_ts = stored_data.get(f"last_updated_{key}")
                if stored_ts is not None:
                    self.last_updated[key] = datetime.fromtimestamp(
                        stored_ts, tz=dt_util.now().tzinfo
                    )
            self.last_seen_cumulative_value = self.last_cumulative_value
            # Restore hour_cumulative_consumption only if from the SAME interval slot.
            # "Same interval" is computed using the configured interval_minutes so that
            # sub-hour intervals (e.g. 30 min) are handled correctly — comparing only
            # clock hours would falsely match e.g. stored=13:10 vs now=13:47 when the
            # interval boundary was at 13:30.
            stored_timestamp = stored_data.get("hour_cumulative_timestamp")
            if stored_timestamp:
                now = dt_util.now()
                stored_time = datetime.fromtimestamp(stored_timestamp, tz=now.tzinfo)

                interval = self.interval_minutes

                def _interval_slot(dt: "datetime") -> tuple:
                    """Return a (day, slot_index) tuple identifying the interval slot."""
                    if interval >= 60:
                        step_hours = interval // 60
                        return (dt.date(), dt.hour // step_hours)
                    else:
                        slot = dt.hour * (60 // interval) + dt.minute // interval
                        return (dt.date(), slot)

                same_interval = _interval_slot(stored_time) == _interval_slot(now)
                # Also keep the legacy same_hour variable for multi-peak catchup logic below
                same_hour = (stored_time.hour == now.hour and stored_time.day == now.day)

                if not self.only_one_peak_per_day:
                    # Multiple-peaks mode: daily_peak is committed at every interval boundary.
                    # If stored data is from a previous interval, commit it now so it
                    # isn't lost, then reset daily_peak for the new interval.
                    # If we are still in the same interval, keep the stored daily_peak so
                    # that the running value is consistent with the restored
                    # hour_cumulative_consumption (avoids bad data on restart).
                    if not same_interval:
                        if self.daily_peak > min(self.monthly_peaks):
                            peaks = self.monthly_peaks + [self.daily_peak]
                            peaks.sort(reverse=True)
                            self.monthly_peaks = peaks[:self.number_of_peaks]
                            _LOGGER.info(
                                "Startup catch-up: committed missed interval peak %s Wh "
                                "from %s to monthly peaks: %s",
                                round(self.daily_peak),
                                stored_time.strftime("%H:%M"),
                                self.monthly_peaks,
                            )
                        self.daily_peak = self.reset_value

                # Restore hour_cumulative_consumption only if we are within the same
                # interval slot AND not at the very boundary (first 2 minutes of the
                # interval). The 2-minute guard avoids seeding a stale accumulator
                # value right after a commit.
                interval_elapsed_minutes = (
                    now.hour * 60 + now.minute
                ) % interval if interval < 60 else now.minute
                at_interval_boundary = interval_elapsed_minutes < 2

                if not sensor_changed and same_interval and not at_interval_boundary:
                    self.hour_cumulative_consumption = stored_data.get("hour_cumulative_consumption", 0.0)
                    # For power-input sensors (W/kW), the trapezoidal integrator uses
                    # _power_integrated_wh as its running total. Seed it with the
                    # restored value so the first post-restart reading continues
                    # from where we left off rather than starting from 0.
                    if self.input_unit in ("W", "kW"):
                        self._power_integrated_wh = self.hour_cumulative_consumption
                    _LOGGER.debug(
                        "Restored hour_cumulative_consumption: %.1f Wh from %s",
                        self.hour_cumulative_consumption,
                        stored_time.strftime("%H:%M:%S"),
                    )
                else:
                    _LOGGER.debug(
                        "Skipped restoring hour_cumulative_consumption "
                        "(hour boundary or different hour/day)"
                    )

                # For cumulative sensors, decide how to handle last_cumulative_value
                # after a restart:
                #
                # Same hour: the stored hour_cumulative_consumption is valid.
                #   We must NOT rebaseline from the current raw reading, because
                #   doing so would zero out the already-accumulated consumption.
                #   Instead, we keep _restart_rebaseline_needed = False so the
                #   next reading is processed normally (delta from last_cumulative_value).
                #
                # Different hour: the stored accumulator is stale (from a previous
                #   hour). Rebaseline from the current raw reading so that
                #   hour_cumulative_consumption starts fresh at 0 for the new hour.
                if not sensor_changed and not self.sensor_resets_every_hour and self.last_cumulative_value is not None:
                    if not same_interval:
                        self._restart_rebaseline_needed = True
                    # same_interval: keep _restart_rebaseline_needed = False (default)

            # Restore previous_hour_rate only if sensor hasn't changed — a rate
            # from a different sensor is meaningless for estimation blending.
            stored_rate = stored_data.get("previous_hour_rate")
            if stored_rate is not None and not sensor_changed:
                self.previous_hour_rate = float(stored_rate)
                _LOGGER.debug(
                    "Restored previous_hour_rate: %.6f Wh/s", self.previous_hour_rate
                )

            # If the stored daily_peak is above reset_value the tariff was already
            # active at some point today — keep the daily peak sensor visible.
            if self.daily_peak > self.reset_value:
                self.tariff_seen_active_today = True

        # Perform any missed resets (HA was off over midnight / month boundary)
        await self._check_and_perform_resets()

        # Initialise target from stored peaks immediately — no waiting for next hour
        # Mark this as startup so target update can be conditional
        self._is_startup = True
        self._force_update_target()
        self._is_startup = False

        # Time-based triggers
        # Schedule hourly updates at local hour boundaries (not UTC)
        self._schedule_next_hourly_update()
        
        # Schedule daily reset at local midnight (not UTC midnight)
        self._schedule_next_daily_reset()

        # Consumption sensor state change listener (real-time updates)
        self._unsub_consumption = async_track_state_change_event(
            self.hass, [self.consumption_sensor], self._async_consumption_changed
        )

        # Check input sensor unit immediately at setup
        self._check_and_warn_input_sensor_unit()

        # Estimation sensor state change listener (if external)
        if self.estimation_sensor:
            self._unsub_estimation = async_track_state_change_event(
                self.hass, [self.estimation_sensor], self._async_estimation_changed
            )

    async def _check_and_perform_resets(self) -> None:
        """Check if resets are needed and perform them (missed while HA was off).
        
        Handles three scenarios:
        - Normal midnight crossing: commit daily peak then reset.
        - Multi-day outage (e.g. 23:57 day 1 → 05:00 day 3): daily peak from before
          the outage was never committed — commit it now before resetting.
        - Monthly boundary: commit daily peak, then reset monthly peaks.
        
        In manual reset mode, automatic resets are skipped entirely.
        In weekly reset mode, monthly boundary resets do not apply.
        """
        now = dt_util.now()

        if self.reset_interval == RESET_INTERVAL_MANUAL:
            # Manual only: no automatic resets on startup either
            if self.last_day is not None and self.last_day != now.day:
                # Still reset daily peak but NOT monthly peaks
                if self.only_one_peak_per_day and self.daily_peak > self.reset_value:
                    peaks = self.monthly_peaks + [self.daily_peak]
                    peaks.sort(reverse=True)
                    self.monthly_peaks = peaks[:self.number_of_peaks]
                await self._reset_peaks(reset_type="daily")
            return

        if self.reset_interval == RESET_INTERVAL_WEEKLY:
            # Weekly: only reset on day boundaries; full reset on Monday
            if self.last_day is not None and self.last_day != now.day:
                if self.only_one_peak_per_day and self.daily_peak > self.reset_value:
                    peaks = self.monthly_peaks + [self.daily_peak]
                    peaks.sort(reverse=True)
                    self.monthly_peaks = peaks[:self.number_of_peaks]
                # If we crossed a Monday while offline, reset monthly peaks too
                if now.isoweekday() == 1:
                    await self._reset_peaks(reset_type="all")
                else:
                    await self._reset_peaks(reset_type="daily")
            return

        # Default: monthly
        if self.last_month is not None and self.last_month != now.month:
            # Month changed while HA was off.
            if self.only_one_peak_per_day and self.daily_peak > self.reset_value:
                peaks = self.monthly_peaks + [self.daily_peak]
                peaks.sort(reverse=True)
                self.monthly_peaks = peaks[:self.number_of_peaks]
                _LOGGER.info(
                    "Startup catch-up (month boundary): committed daily peak %s Wh "
                    "to monthly peaks before monthly reset: %s",
                    round(self.daily_peak),
                    self.monthly_peaks,
                )
            await self._reset_peaks(reset_type="monthly")

        elif self.last_day is not None and self.last_day != now.day:
            # Day changed (including multi-day outage) while HA was off.
            if self.only_one_peak_per_day and self.daily_peak > self.reset_value:
                peaks = self.monthly_peaks + [self.daily_peak]
                peaks.sort(reverse=True)
                self.monthly_peaks = peaks[:self.number_of_peaks]
                self.last_updated["monthly_peaks"] = dt_util.now()
                _LOGGER.info(
                    "Startup catch-up (day boundary): committed daily peak %s Wh "
                    "to monthly peaks: %s",
                    round(self.daily_peak),
                    self.monthly_peaks,
                )
            await self._reset_peaks(reset_type="daily")

    def _schedule_next_hourly_update(self) -> None:
        """Schedule next interval update at the next configured boundary.

        Boundaries are aligned to the start of the hour (minute 0).
        E.g. interval=15 → fires at :00, :15, :30, :45.
             interval=60 → fires at :00 (top of each hour, original behaviour).
             interval=120 → fires at :00 of every other hour.
        """
        if self._unsub_hourly:
            self._unsub_hourly()

        now = dt_util.now()
        interval = self.interval_minutes

        if interval >= 60:
            # Align to hour boundaries, step by interval/60 hours
            step_hours = interval // 60
            next_boundary = now.replace(minute=0, second=0, microsecond=0)
            while next_boundary <= now:
                next_boundary = next_boundary + timedelta(hours=step_hours)
        else:
            # Align to sub-hour boundaries within each hour
            current_minute = now.minute
            next_minute = ((current_minute // interval) + 1) * interval
            if next_minute < 60:
                next_boundary = now.replace(minute=next_minute, second=0, microsecond=0)
            else:
                next_boundary = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        _LOGGER.debug(
            "Scheduling next interval update at %s (interval=%d min)",
            next_boundary.strftime("%Y-%m-%d %H:%M:%S %Z"),
            interval,
        )

        self._unsub_hourly = async_track_point_in_time(
            self.hass, self._async_update_hourly_and_reschedule, next_boundary
        )

    async def _async_update_hourly_and_reschedule(self, now: datetime) -> None:
        """Run hourly update and schedule next one."""
        await self._async_update_hourly(now)
        self._schedule_next_hourly_update()  # Schedule next hour

    async def async_shutdown(self) -> None:
        """Shut down the coordinator and release all subscriptions."""
        for attr in ("_unsub_hourly", "_unsub_daily", "_unsub_estimation", "_unsub_consumption"):
            unsub = getattr(self, attr, None)
            if unsub is not None:
                try:
                    unsub()
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("Exception while unsubscribing %s (ignored)", attr)
                setattr(self, attr, None)
        await self._async_save_data()

    # ------------------------------------------------------------------
    # Input sensor unit validation
    # ------------------------------------------------------------------

    def _check_and_warn_input_sensor_unit(self) -> None:
        """Check the consumption sensor's reported unit and warn if unexpected.

        Called once at setup.  The warning is not repeated on every state change
        to avoid log spam.
        """
        if self._input_unit_warned:
            return
        state = self.hass.states.get(self.consumption_sensor)
        if state is None:
            # Sensor not yet available at startup — will be checked on first event
            return
        attrs = getattr(state, "attributes", None) or {}
        unit = attrs.get("unit_of_measurement")
        check_input_sensor_unit(self.consumption_sensor, unit, _LOGGER)
        self._input_unit_warned = True

    # ------------------------------------------------------------------
    # Listener management
    # ------------------------------------------------------------------

    def add_listener(self, listener) -> None:
        """Add a listener for state updates."""
        self._listeners.append(listener)

    def remove_listener(self, listener) -> None:
        """Remove a listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def _async_notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        self.last_updated["state"] = dt_util.now()
        for listener in self._listeners:
            listener()

    async def _async_notify_sensor_unavailable(self) -> None:
        """Fire a persistent notification when the consumption sensor goes unavailable.

        The notification is only created if one is not already showing, so repeated
        unavailability events (e.g. sensor flapping) don't stack up.
        """
        from homeassistant.components.persistent_notification import async_create
        instance = self.entry.data.get("name", "Peak Monitor")
        notification_id = f"peak_monitor_{self.entry.entry_id}_sensor_unavailable"
        already_shown = self.hass.states.get(f"persistent_notification.{notification_id}") is not None
        if not already_shown:
            async_create(
                self.hass,
                title=f"⚠️ Peak Monitor — Consumption sensor unavailable ({instance})",
                message=(
                    f"The consumption sensor **`{self.consumption_sensor}`** has become "
                    f"unavailable or reported an unknown state.\n\n"
                    f"**What happens:** Live output sensors (estimation, relative, "
                    f"percentage, hour consumption) are now showing as unavailable. "
                    f"Committed peak values are unaffected.\n\n"
                    f"The notification will clear automatically when the sensor recovers."
                ),
                notification_id=notification_id,
            )

    async def _async_dismiss_sensor_unavailable_notification(self) -> None:
        """Dismiss the sensor-unavailable notification when the sensor recovers."""
        from homeassistant.components.persistent_notification import async_dismiss
        notification_id = f"peak_monitor_{self.entry.entry_id}_sensor_unavailable"
        async_dismiss(self.hass, notification_id)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    async def _async_save_data(self) -> None:
        """Save persistent data to storage."""
        now = dt_util.now()
        data = {
            "consumption_sensor": self.consumption_sensor,
            "daily_peak": self.daily_peak,
            "daily_sub_peaks": self.daily_sub_peaks,
            "monthly_peaks": self.monthly_peaks,
            "last_month": now.month,
            "last_day": now.day,
            "last_cumulative_value": self.last_cumulative_value,
            "hour_cumulative_consumption": self.hour_cumulative_consumption,
            "hour_cumulative_timestamp": now.timestamp(),
            "previous_hour_rate": self.previous_hour_rate,
            # Stored to detect sensor swaps on next startup
            "consumption_sensor": self.consumption_sensor,
        }
        # Persist last_updated timestamps for sensors that survive restarts
        for key in ("daily_peak", "daily_sub_peaks", "monthly_peaks", "target"):
            ts = self.last_updated.get(key)
            if ts is not None:
                data[f"last_updated_{key}"] = ts.timestamp()
        await self.store.async_save(data)

    # ------------------------------------------------------------------
    # Unit conversion helper
    # ------------------------------------------------------------------

    def _convert_to_wh(self, value: float) -> float:
        """Convert an input sensor value to Wh based on configured input_unit.
        
        For energy inputs (Wh/kWh): direct conversion.
        For power inputs (W/kW): returns instantaneous watts — integration
        is handled separately in the consumption event handler.
        """
        if self.input_unit == "kWh":
            return value * 1000.0
        if self.input_unit == "kW":
            return value * 1000.0  # returns watts
        return value  # Wh or W (raw)
    
    def _convert_to_output_unit(self, value_wh: float) -> float:
        """Convert a Wh value to the configured output unit (W or kW).
        
        Internally all values are stored in Wh (energy per hour = average watts).
        W and kW are the standard display units for power grid tariffs.
        """
        if self.output_unit == "kW":
            return value_wh / 1000.0
        return value_wh
    
    def get_output_unit_string(self) -> str:
        """Get the output unit string for sensor display."""
        return self.output_unit
    
    def get_output_precision(self) -> int:
        """Get the suggested display precision for the output unit."""
        if self.output_unit == "kW":
            return 3  # Show 3 decimals for kW
        return 0  # Show 0 decimals for W

    # ------------------------------------------------------------------
    # Consumption event handler (real-time, every sensor update)
    # ------------------------------------------------------------------

    async def _async_consumption_changed(self, event) -> None:
        """Handle consumption sensor state changes.

        Guarded by an asyncio.Lock to serialise rapid back-to-back updates and
        prevent race conditions when multiple state change events fire within a
        short window (e.g. zigbee sensors reporting every few seconds).
        """
        async with self._processing_lock:
            await self._async_handle_consumption_event(event)

    async def _async_handle_consumption_event(self, event) -> None:
        """Inner consumption handler — called with the processing lock held."""
        now = dt_util.now()

        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            # Log when source sensor becomes unavailable
            old_state = event.data.get("old_state")
            if old_state and old_state.state not in ("unknown", "unavailable", None):
                _LOGGER.warning(
                    "Consumption sensor '%s' became unavailable (was: %s)",
                    self.consumption_sensor, old_state.state
                )
            # Mark consumption sensor as unavailable and notify HA + user
            if self.consumption_sensor_available:
                self.consumption_sensor_available = False
                await self._async_notify_sensor_unavailable()
            await self._async_notify_listeners()
            return

        # Mark consumption sensor as available
        if not self.consumption_sensor_available:
            _LOGGER.info(
                "Consumption sensor '%s' is now available again",
                self.consumption_sensor
            )
            self.consumption_sensor_available = True
            await self._async_dismiss_sensor_unavailable_notification()

        # Warn once if the sensor's reported unit is unexpected
        if not self._input_unit_warned:
            attrs = getattr(new_state, "attributes", None) or {}
            unit = attrs.get("unit_of_measurement")
            check_input_sensor_unit(self.consumption_sensor, unit, _LOGGER)
            self._input_unit_warned = True

        try:
            raw_value = float(new_state.state)
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Failed to parse consumption sensor '%s' value '%s': %s",
                self.consumption_sensor, new_state.state, err
            )
            return

        # --- Power input mode (W or kW): integrate to get Wh ---
        is_power_input = self.input_unit in ("W", "kW")
        if is_power_input:
            power_watts = raw_value * 1000.0 if self.input_unit == "kW" else raw_value
            if self._last_power_sample is None:
                # First reading — seed without accumulation
                self._last_power_sample = (now, power_watts)
                self.has_received_reading = True
                await self._async_notify_listeners()
                return
            last_ts, last_watts = self._last_power_sample
            dt_seconds = (now - last_ts).total_seconds()
            if dt_seconds > 0:
                # Trapezoidal integration: average power * elapsed time
                avg_watts = (last_watts + power_watts) / 2.0
                wh_increment = avg_watts * dt_seconds / 3600.0
                self._power_integrated_wh += wh_increment
                self.hour_cumulative_consumption = self._power_integrated_wh
            self._last_power_sample = (now, power_watts)
            consumption_this_hour = self._power_integrated_wh
            # Persist after every power reading so restarts always have a
            # recent hour_cumulative_consumption to restore from.
            await self._async_save_data()
        else:
            # Energy input mode (Wh or kWh)
            raw_value_wh = raw_value * 1000.0 if self.input_unit == "kWh" else raw_value

            # --- Determine consumption_this_hour (always needed for estimation) ---
            if self.sensor_resets_every_hour:
                # Sensor resets each hour: the value IS consumption this hour
                consumption_this_hour = raw_value_wh
            else:
                # Cumulative sensor: consumption = current - hour-start baseline
                if self.last_cumulative_value is None:
                    # No baseline yet — seed it and skip
                    self.last_cumulative_value = raw_value_wh
                    self.last_seen_cumulative_value = raw_value_wh
                    await self._async_save_data()
                    return

                # After a cross-hour restart, re-baseline from the current raw reading
                if self._restart_rebaseline_needed:
                    _LOGGER.info(
                        "Restart rebaseline (cross-hour): resetting cumulative baseline "
                        "from %s to %s Wh; hour consumption starts at 0",
                        self.last_cumulative_value, raw_value_wh
                    )
                    self.last_cumulative_value = raw_value_wh
                    self.last_seen_cumulative_value = raw_value_wh
                    self.hour_cumulative_consumption = 0.0
                    self._restart_rebaseline_needed = False
                    await self._async_save_data()
                    await self._async_notify_listeners()
                    return

                consumption_this_hour = raw_value_wh - self.last_cumulative_value

                if consumption_this_hour < 0:
                    # Sensor reset (e.g. new month) — re-baseline and skip
                    _LOGGER.info(
                        "Cumulative sensor reset detected (was %s, now %s). Re-baselining.",
                        self.last_cumulative_value, raw_value_wh
                    )
                    self.last_cumulative_value = raw_value_wh
                    self.last_seen_cumulative_value = raw_value_wh
                    self.hour_cumulative_consumption = 0.0
                    await self._async_save_data()
                    await self._async_notify_listeners()
                    return

                self.last_seen_cumulative_value = raw_value_wh

            self.hour_cumulative_consumption = consumption_this_hour
        self.last_updated["hour_consumption"] = dt_util.now()
        self.has_received_reading = True

        # --- Update internal estimation (always, even when tariff inactive) ---
        if not self.estimation_sensor:
            self.consumption_samples.append((now, consumption_this_hour))

            # Keep only samples from last 15 minutes
            cutoff = now.timestamp() - 900
            self.consumption_samples = [
                (ts, val) for ts, val in self.consumption_samples
                if ts.timestamp() >= cutoff
            ]
            
            # Calculate internal estimation (interval-aware)
            estimated = calculate_internal_estimation(
                self.consumption_samples,
                now,
                previous_hour_rate=self.previous_hour_rate,
                interval_minutes=self.interval_minutes,
            )
            
            # Store in estimation_history
            if not hasattr(self, 'estimation_history'):
                self.estimation_history: list[float] = []
            self.estimation_history = [estimated]

            # Estimation is now reliable — we have at least one real sample
            # (or previous_hour_rate is available for blending).
            self._estimation_unreliable = False

        # --- Only update peaks if tariff is active ---
        tariff_state = self.get_tariff_active_state(now)
        if tariff_state == ACTIVE_STATE_OFF:
            # Tariff is off — skip peak updates but notify for estimation sensor
            await self._async_notify_listeners()
            return

        # Tariff is active or reduced — mark that it has been seen today.
        # This unlocks the daily peak sensor for the rest of the day.
        self.tariff_seen_active_today = True

        # --- Tariff is active - update peaks ---
        # Apply reduction factor if in any reduced state:
        # daily time window, weekend reduced, holiday reduced, or external reduced sensor
        if tariff_state == ACTIVE_STATE_REDUCED:
            adjusted_consumption = consumption_this_hour * self.reduced_factor
        else:
            adjusted_consumption = consumption_this_hour

        # Use epsilon-based comparison to avoid flapping near boundaries
        # Only update if new value is meaningfully higher (> 1 Wh difference)
        PEAK_UPDATE_EPSILON = 1.0  # Wh

        # --- Update daily peak ---
        if self.only_one_peak_per_day and self.daily_peaks_averaged > 1:
            # Averaging mode: daily_sub_peaks is updated only at hourly boundaries
            # (in _async_update_hourly). The live tariff/cost is computed on-demand
            # via get_live_daily_peak() which blends sub_peaks with the current
            # hour_cumulative_consumption. We do NOT call _force_update_target here —
            # the target is defined by committed sub_peaks and only changes at hour
            # boundaries, not on every reading.
            pass
        else:
            # Standard single-peak mode
            if adjusted_consumption > (self.daily_peak + PEAK_UPDATE_EPSILON):
                old_peak = self.daily_peak
                self.daily_peak = adjusted_consumption
                self.last_updated["daily_peak"] = dt_util.now()
                self._update_target()
                await self._async_save_data()
                _LOGGER.debug("Daily peak updated: %s -> %s Wh (raw: %s)",
                              old_peak, self.daily_peak, consumption_this_hour)

        # Always notify for real-time sensor updates
        await self._async_notify_listeners()

    async def _async_estimation_changed(self, event) -> None:
        """Handle external estimation sensor state changes."""
        await self._async_notify_listeners()

    # ------------------------------------------------------------------
    # Hourly update (fires at :00 of every hour)
    # ------------------------------------------------------------------

    async def _async_update_hourly(self, now: datetime) -> None:
        """Update at each interval boundary (configurable: 6, 12, 15, 20, 30, 60, or 120 minutes)."""
        # Use the caller-provided 'now' (from the scheduler callback).
        # This allows tests to inject a specific time and avoids a second
        # call to dt_util.now() which could disagree with the scheduler's time.
        if now is None:
            now = dt_util.now()

        # --- Save the rate from the ending hour before we reset anything ---
        # This is used as fallback so estimation doesn't show 0 at hour start.
        if len(self.consumption_samples) >= 2:
            first_ts, first_val = self.consumption_samples[0]
            last_ts, last_val = self.consumption_samples[-1]
            time_diff = last_ts.timestamp() - first_ts.timestamp()
            if time_diff > 1:
                self.previous_hour_rate = (last_val - first_val) / time_diff
            # else: keep whatever previous_hour_rate we had

        # --- Multiple peaks per day mode: Update monthly peaks if hour consumption is high enough ---
        if not self.only_one_peak_per_day:
            # Get the hourly consumption that just ended.
            hourly_consumption = self.hour_cumulative_consumption

            # Determine the tariff state for the interval that just ended.
            # The callback fires at the boundary, so we check one minute before
            # to get the state of the ending interval.
            ending_hour_time = now - timedelta(minutes=1)
            tariff_state = self.get_tariff_active_state(ending_hour_time)

            if tariff_state == ACTIVE_STATE_OFF:
                # Tariff was inactive during the ending hour — do NOT commit this
                # hour's consumption as a peak. This prevents night-time or
                # out-of-season hours from polluting the monthly peak list.
                _LOGGER.debug(
                    "Multiple peaks mode: Skipping hourly commit — tariff was inactive "
                    "during the ending hour (%s). Consumption: %s Wh",
                    ending_hour_time.strftime("%H:%M"),
                    round(hourly_consumption),
                )
            else:
                # Apply reduction factor if the tariff was in reduced state this hour
                if tariff_state == ACTIVE_STATE_REDUCED and self.reduced_factor > 0:
                    adjusted_consumption = hourly_consumption * self.reduced_factor
                else:
                    adjusted_consumption = hourly_consumption

                # Check if this hour's consumption qualifies as a monthly peak
                if adjusted_consumption > min(self.monthly_peaks):
                    # Add this hour's consumption to the list and resort
                    peaks = self.monthly_peaks + [adjusted_consumption]
                    peaks.sort(reverse=True)
                    self.monthly_peaks = peaks[:self.number_of_peaks]
                    self.last_updated["monthly_peaks"] = dt_util.now()

                    _LOGGER.info(
                        "Multiple peaks mode: Hourly consumption %s Wh (adjusted: %s Wh) qualifies as monthly peak. "
                        "Updated monthly peaks: %s",
                        round(hourly_consumption), round(adjusted_consumption), self.monthly_peaks
                    )

            # Reset daily_peak every hour in this mode (it's not used/published)
            self.daily_peak = self.reset_value

        # --- Averaging mode: commit completed hour to daily_sub_peaks ---
        # In only_one_peak_per_day + daily_peaks_averaged > 1 mode, sub_peaks
        # tracks the top-N completed-hour readings within the current day.
        # We update it here (hourly boundary) rather than on every sensor event
        # to avoid "braid" flickering in graphs.
        if self.only_one_peak_per_day and self.daily_peaks_averaged > 1:
            hourly_consumption = self.hour_cumulative_consumption
            ending_hour_time = now - timedelta(minutes=1)
            tariff_state_hour = self.get_tariff_active_state(ending_hour_time)

            if tariff_state_hour != ACTIVE_STATE_OFF:
                if tariff_state_hour == ACTIVE_STATE_REDUCED and self.reduced_factor > 0:
                    adjusted_hour = hourly_consumption * self.reduced_factor
                else:
                    adjusted_hour = hourly_consumption

                # Only admit the hour if it beats the current weakest sub-peak
                if adjusted_hour > min(self.daily_sub_peaks) + 1.0:
                    sub = sorted(self.daily_sub_peaks + [adjusted_hour], reverse=True)
                    self.daily_sub_peaks = sub[:self.daily_peaks_averaged]
                    self.last_updated["daily_sub_peaks"] = dt_util.now()
                    _LOGGER.info(
                        "Averaging mode: hourly reading %s Wh committed to daily_sub_peaks: %s",
                        round(adjusted_hour), self.daily_sub_peaks,
                    )

        # --- Snapshot cumulative baseline at hour boundary ---
        if not self.sensor_resets_every_hour:
            consumption_state = self.hass.states.get(self.consumption_sensor)
            if consumption_state and consumption_state.state not in ("unknown", "unavailable", None):
                try:
                    new_baseline = self._convert_to_wh(float(consumption_state.state))
                    # Handle reset at hour boundary
                    if self.last_cumulative_value is not None and new_baseline < self.last_cumulative_value:
                        _LOGGER.info(
                            "Cumulative sensor reset at hour boundary (was %s, now %s).",
                            self.last_cumulative_value, new_baseline
                        )
                    self.last_cumulative_value = new_baseline
                    self.last_seen_cumulative_value = new_baseline
                    await self._async_save_data()
                except (ValueError, TypeError):
                    pass

        # --- Reset hour tracking ---
        self.consumption_samples = []
        self.hour_cumulative_consumption = 0.0
        # Reset power integration accumulator for power-input mode
        self._power_integrated_wh = 0.0
        self._last_power_sample = None
        self.last_updated["hour_consumption"] = dt_util.now()

        # Save immediately after reset so that if HA restarts within this same
        # interval slot, the stored hour_cumulative_consumption is 0 (not the
        # stale end-of-last-interval value that was saved before the reset).
        await self._async_save_data()

        # --- Immediately recompute estimation for the new hour ---
        # calculate_internal_estimation with empty samples + previous_hour_rate
        # returns rate * 3600, which is the best guess at :00:00 before any new
        # readings arrive. This prevents downstream sensors (relative, percentage,
        # cost increase) from showing stale values from the ended hour.
        if not self.estimation_sensor:
            boundary_estimate = calculate_internal_estimation(
                [],  # no samples yet in the new interval
                now,
                previous_hour_rate=self.previous_hour_rate,
                interval_minutes=self.interval_minutes,
            )
            if not hasattr(self, 'estimation_history'):
                self.estimation_history: list[float] = []
            self.estimation_history = [boundary_estimate]

            # Reliable if we have a rate to base the estimate on; unreliable
            # only if we have neither samples nor a previous-hour rate.
            self._estimation_unreliable = self.previous_hour_rate is None

        # --- Update target ---
        self._update_target()

        # Notify so sensors pick up new state immediately
        await self._async_notify_listeners()

    # ------------------------------------------------------------------
    # Daily update (fires at local midnight)
    # ------------------------------------------------------------------

    def _schedule_next_daily_reset(self) -> None:
        """Schedule the next daily reset at local midnight."""
        if self._unsub_daily:
            self._unsub_daily()
        
        # Get current local time
        now = dt_util.now()
        
        # Calculate next local midnight
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=5, microsecond=0
        )
        
        _LOGGER.debug(
            "Scheduling next daily reset at %s (local time, timezone: %s)",
            next_midnight.strftime("%Y-%m-%d %H:%M:%S %Z"),
            next_midnight.tzinfo
        )
        
        # Schedule the callback
        self._unsub_daily = async_track_point_in_time(
            self.hass, self._async_update_daily, next_midnight
        )

    async def _async_update_daily(self, now: datetime) -> None:
        """Update at midnight — commit daily peak to monthly peaks and reset."""
        # Use the caller-provided 'now' (from the scheduler callback).
        # This allows tests to inject a specific time.
        if now is None:
            now = dt_util.now()
        
        # FIRST: Commit current daily peak to monthly peaks (only in normal mode)
        # This must happen BEFORE monthly reset to avoid committing previous month's last day to current month
        if self.only_one_peak_per_day:
            if self.daily_peaks_averaged > 1:
                # Averaging mode: commit the live blended average (sub-peaks + last
                # hour's final reading) as the daily value.
                # hour_cumulative_consumption holds the last hour's final reading at
                # this point (midnight fires after the 23:00 hourly callback).
                last_hour_wh = self.hour_cumulative_consumption
                if self.get_tariff_active_state() == ACTIVE_STATE_REDUCED and self.reduced_factor > 0:
                    last_hour_wh = last_hour_wh * self.reduced_factor
                candidates = sorted(self.daily_sub_peaks + [last_hour_wh], reverse=True)
                final_top_n = candidates[:self.daily_peaks_averaged]
                committed_value = sum(final_top_n) / len(final_top_n)
                _LOGGER.info(
                    "Averaging mode: midnight commit — sub_peaks %s + last_hour %s Wh "
                    "→ top-%s avg = %s Wh",
                    self.daily_sub_peaks, round(last_hour_wh),
                    self.daily_peaks_averaged, round(committed_value),
                )
            else:
                committed_value = self.daily_peak

            peaks = self.monthly_peaks + [committed_value]
            peaks.sort(reverse=True)
            self.monthly_peaks = peaks[:self.number_of_peaks]
            self.last_updated["monthly_peaks"] = dt_util.now()

            _LOGGER.info("Committed daily peak %s Wh to monthly peaks: %s",
                         round(committed_value), self.monthly_peaks)
        
        # SECOND: Determine if a reset should happen based on reset_interval
        should_reset_monthly = False
        should_reset_weekly = False

        if self.reset_interval == RESET_INTERVAL_MANUAL:
            # Manual only: never auto-reset monthly peaks
            pass
        elif self.reset_interval == RESET_INTERVAL_WEEKLY:
            # Reset on Monday (isoweekday 1)
            if now.isoweekday() == 1:
                should_reset_weekly = True
                _LOGGER.info("Weekly reset triggered on Monday %s", now.date())
        else:
            # Default: monthly
            if self.last_month is not None and self.last_month != now.month:
                should_reset_monthly = True
                _LOGGER.info("Monthly reset triggered: month changed from %s to %s",
                             self.last_month, now.month)

        # THIRD: Perform resets
        if should_reset_monthly or should_reset_weekly:
            self.monthly_peaks = [self.reset_value] * self.number_of_peaks
            self.daily_peak = self.reset_value
            self.daily_sub_peaks = [self.reset_value] * self.daily_peaks_averaged
            self.last_month = now.month
            _LOGGER.info("Reset monthly peaks AND daily peak to %s Wh", self.reset_value)
        else:
            # Just reset daily peak
            self.daily_peak = self.reset_value
            self.daily_sub_peaks = [self.reset_value] * self.daily_peaks_averaged
            _LOGGER.info("Reset daily peak to %s Wh", self.reset_value)

        # Update tracking
        self.last_day = now.day
        self.last_month = now.month
        self.tariff_seen_active_today = False

        self._force_update_target()

        await self._async_save_data()
        await self._async_notify_listeners()
        
        # Schedule the next daily reset
        self._schedule_next_daily_reset()

    # ------------------------------------------------------------------
    # Peak resets
    # ------------------------------------------------------------------

    async def _reset_peaks(self, reset_type: str = "daily") -> None:
        """Reset peaks based on type: 'daily', 'monthly', or 'all'."""
        now = dt_util.now()

        if reset_type in ("daily", "all"):
            self.daily_peak = self.reset_value
            self.daily_sub_peaks = [self.reset_value] * self.daily_peaks_averaged
            self.last_day = now.day
            self.tariff_seen_active_today = False
            _LOGGER.info("Reset daily peak to %s Wh", self.reset_value)

        if reset_type in ("monthly", "all"):
            self.monthly_peaks = [self.reset_value] * self.number_of_peaks
            self.last_month = now.month
            _LOGGER.info("Reset monthly peaks to %s Wh", self.reset_value)

            if reset_type == "monthly":
                self.daily_peak = self.reset_value
                self.last_day = now.day
                self.tariff_seen_active_today = False

        self._force_update_target()
        await self._async_save_data()
        await self._async_notify_listeners()

    # ------------------------------------------------------------------
    # Tariff state logic
    # ------------------------------------------------------------------

    def get_tariff_active_state(self, now: datetime | None = None) -> str:
        """Get the current tariff active state.

        Priority order:
        1. Month check
        2. Holiday / holiday evening → holiday_behavior (off or reduced)
        3. Weekend → weekend_behavior
        4. Hour range → active / reduced / off
        """
        state, _ = self.get_tariff_active_state_with_reasons(now)
        return state
    
    def get_tariff_active_state_with_reasons(self, now: datetime | None = None) -> tuple[str, list[str]]:
        """Get the current tariff active state along with reasons for inactive/reduced.
        
        Returns:
            tuple: (state, reasons) where state is ACTIVE_STATE_ON/OFF/REDUCED
                   and reasons is a list like ["Excluded month", "Weekend", "Holiday", "Time of day"]
        """
        if now is None:
            now = dt_util.now()

        reasons = []

        # External mute sensor check - takes priority over everything
        if self.external_mute_sensor:
            mute_state = self.hass.states.get(self.external_mute_sensor)
            if mute_state and mute_state.state == "on":
                reasons.append(REASON_EXTERNAL_MUTE)
                return ACTIVE_STATE_OFF, reasons

        # Month check
        if now.month not in self.active_months:
            reasons.append(REASON_EXCLUDED_MONTH)
            return ACTIVE_STATE_OFF, reasons

        from .holidays import is_swedish_holiday, is_holiday_evening

        # Holidays
        if is_swedish_holiday(now, self.exclude_holidays):
            reasons.append(REASON_HOLIDAY)
            if self.holiday_behavior == BEHAVIOR_REDUCED_TARIFF:
                return ACTIVE_STATE_REDUCED, reasons
            return ACTIVE_STATE_OFF, reasons

        # Holiday evenings
        if is_holiday_evening(now, self.exclude_holiday_evenings):
            reasons.append(REASON_HOLIDAY)
            if self.holiday_behavior == BEHAVIOR_REDUCED_TARIFF:
                return ACTIVE_STATE_REDUCED, reasons
            return ACTIVE_STATE_OFF, reasons

        # Weekends
        if now.isoweekday() > 5:
            # Determine if we are within the weekend active interval.
            # If start_hour == end_hour, the entire day is considered within the interval.
            if self.weekend_start_hour == self.weekend_end_hour:
                in_weekend_interval = True
            else:
                in_weekend_interval = is_time_in_range(now, self.weekend_start_hour, self.weekend_end_hour)

            # Check if daily reduced window should apply on weekends too.
            # If so, and we're currently in the reduced time window, return REDUCED
            # regardless of weekend_behavior — inactive is still dominant.
            if self.reduced_also_on_weekends and self.reduced_tariff_enabled:
                in_reduced_time_now = is_time_in_range(now, self.reduced_start_hour, self.reduced_end_hour)
                if in_reduced_time_now:
                    reasons.append(REASON_TIME_OF_DAY)
                    return ACTIVE_STATE_REDUCED, reasons

            if not in_weekend_interval:
                # Outside the weekend active interval → tariff is inactive
                reasons.append(REASON_TIME_OF_DAY)
                return ACTIVE_STATE_OFF, reasons

            if self.weekend_behavior == BEHAVIOR_NO_TARIFF:
                reasons.append(REASON_WEEKEND)
                return ACTIVE_STATE_OFF, reasons
            elif self.weekend_behavior == BEHAVIOR_REDUCED_TARIFF:
                reasons.append(REASON_WEEKEND)
                return ACTIVE_STATE_REDUCED, reasons
            # else "full_tariff" → fall through to hour logic

        # Hour ranges
        # Special case: if start_hour == end_hour, run 24 hours
        if self.active_start_hour == self.active_end_hour:
            in_active = True
        else:
            in_active = is_time_in_range(now, self.active_start_hour, self.active_end_hour)
        
        # Check if reduced tariff should be active based on time-of-day
        in_reduced_time = (self.reduced_tariff_enabled and
                          is_time_in_range(now, self.reduced_start_hour, self.reduced_end_hour))
        
        # Check external reduced sensor
        in_reduced_external = False
        if self.external_reduced_sensor:
            reduced_state = self.hass.states.get(self.external_reduced_sensor)
            if reduced_state and reduced_state.state == "on":
                in_reduced_external = True
        
        # Combine reduced conditions
        in_reduced = in_reduced_time or in_reduced_external

        # Reduced window takes priority over the active-hour cutoff:
        # A reduced window (e.g. 21–06) can extend beyond the active window (e.g. 06–22),
        # so those overnight hours should count as REDUCED, not OFF.
        if in_reduced:
            reasons.append(REASON_TIME_OF_DAY if in_reduced_time else REASON_EXTERNAL_CONTROL)
            return ACTIVE_STATE_REDUCED, reasons

        # If we're not in active hours (and not reduced), tariff is off
        if not in_active:
            reasons.append(REASON_TIME_OF_DAY)
            return ACTIVE_STATE_OFF, reasons
        
        # In active hours with full tariff
        return ACTIVE_STATE_ON, reasons

    def is_tariff_active(self, now: datetime | None = None) -> bool:
        """Check if the tariff is currently active (any state except off)."""
        return self.get_tariff_active_state(now) != ACTIVE_STATE_OFF

    # ------------------------------------------------------------------
    # Tariff / target / estimation accessors
    # ------------------------------------------------------------------

    def get_current_tariff(self, include_today: bool = False) -> float:
        """Calculate the current tariff (average of top N monthly peaks).

        If include_today is True, today's live daily peak (from get_live_daily_peak)
        is included when it would displace the current minimum monthly peak.
        In averaging mode this uses the blended estimate so the tariff sensor
        updates in real time as the current hour's consumption rises.
        """
        if include_today:
            live_daily = self.get_live_daily_peak()
            if live_daily > min(self.monthly_peaks):
                peaks = sorted(self.monthly_peaks + [live_daily], reverse=True)
                peaks = peaks[:self.number_of_peaks]
                return sum(peaks) / len(peaks)

        return sum(self.monthly_peaks) / len(self.monthly_peaks)

    def is_daily_peak_affecting_now(self) -> bool:
        """Return True when current estimated consumption already exceeds today's committed daily_peak.

        When True, the daily peak sensor's last_updated should reflect that the
        value is being influenced right now (uncommitted). The estimate must be
        reliable for this to be meaningful.
        """
        if not self.is_tariff_active():
            return False
        estimated = self.get_estimated_consumption()
        if estimated is None:
            return False
        return estimated > self.daily_peak

    def is_monthly_average_affecting_now(self) -> bool:
        """Return True when today's daily_peak is already influencing the monthly average.

        Uses the committed daily_peak so this is stable between hourly commits.
        The live blended value is used separately inside get_current_tariff().
        """
        return self.daily_peak > min(self.monthly_peaks)

    def get_target_consumption(self) -> float:
        """Get the target consumption threshold.

        In reduced mode the displayed target is scaled up so the user can see
        how much they can actually consume (the reduction is applied when
        recording the peak, not when comparing).
        """
        if not self.is_tariff_active():
            return 0.0

        base_target = self.cached_target

        if self.get_tariff_active_state() == ACTIVE_STATE_REDUCED and self.reduced_factor > 0:
            return base_target / self.reduced_factor

        return base_target

    def _update_target(self) -> None:
        """Update cached target only once per interval period.

        Called from the consumption event handler on every reading — the interval
        guard means the target only recalculates at interval boundaries, matching
        the commit schedule: target is stable within each interval period.
        """
        now = dt_util.now()
        interval = self.interval_minutes
        # Compute which interval slot we're currently in
        if interval >= 60:
            current_slot = now.hour // (interval // 60)
        else:
            current_slot = now.hour * (60 // interval) + now.minute // interval
        if self.last_target_update_hour == current_slot:
            return
        self._force_update_target()

    def get_live_daily_peak(self) -> float:
        """Return the live daily peak value for display and tariff calculation.

        In standard mode (daily_peaks_averaged == 1):
            Returns self.daily_peak directly.

        In averaging mode (daily_peaks_averaged > 1):
            daily_sub_peaks holds the top-N completed-hour readings from earlier
            today.  The current hour's interval consumption participates *live*
            only when it would improve (increase) the average — and only when the
            tariff is currently ACTIVE (not reduced, not inactive).

        Rules:
          1. Tariff must be ACTIVE — returns committed average when inactive/reduced.
          2. Uses hour_cumulative_consumption (interval sensor), not the estimation.
          3. Only displaces the weakest sub-peak slot if interval > min(sub_peaks).
          4. Result is monotone: always >= committed sub-peaks average.

        Example (N=2, sub_peaks=[2000, 1000], interval=1200):
            sorted([2000, 1000, 1200])[:2] = [2000, 1200]
            live_avg = (2000 + 1200) / 2 = 1600 Wh  ← replaces 1000
        Example (N=2, sub_peaks=[2000, 1000], interval=800):
            800 < min(sub_peaks)=1000 → no blend
            committed_avg = (2000 + 1000) / 2 = 1500 Wh
        """
        if not (self.only_one_peak_per_day and self.daily_peaks_averaged > 1):
            return self.daily_peak

        committed_avg = sum(self.daily_sub_peaks) / len(self.daily_sub_peaks)

        # Rule 1: only blend when tariff is actively ACTIVE (not reduced, not off)
        if self.get_tariff_active_state() != ACTIVE_STATE_ON:
            return committed_avg

        interval_wh = self.hour_cumulative_consumption

        # Rule 3: only blend if interval beats the current weakest sub-peak
        if interval_wh <= min(self.daily_sub_peaks):
            return committed_avg

        # Blend: top-N from (committed sub-peaks + interval reading)
        candidates = sorted(self.daily_sub_peaks + [interval_wh], reverse=True)
        live_top_n = candidates[:self.daily_peaks_averaged]
        live_avg = sum(live_top_n) / len(live_top_n)

        # Rule 4: result can only increase, never decrease
        return max(committed_avg, live_avg)

    def _force_update_target(self) -> None:
        """Unconditionally recalculate and cache the base target.

        Called on startup, midnight reset, interval boundary, and manual reset.
        Updated at most once per interval (guarded by _update_target).

        Averaging mode (only_one_peak_per_day + daily_peaks_averaged > 1):
        -----------------------------------------------------------------------
        Case A — all sub-peaks < lowest_monthly:
            Target = lowest_monthly
            (no sub-peak qualifies yet; stay below the floor)

        Case B — at least one sub-peak >= lowest_monthly, but daily_peak < lowest_monthly:
            daily_peak = avg(top-N sub-peaks).  We want avg(top-N including today)
            to stay <= lowest_monthly.  The threshold value T satisfies:
                (sum_of_top_N_excl_weakest + T) / N = lowest_monthly
            i.e. T = N * lowest_monthly − sum(top_{N-1} largest sub-peaks)
            Target = max(T, smallest_sub_peak)
            (cannot be lower than the weakest committed slot)

        Case C — daily_peak >= lowest_monthly:
            The average already qualifies; target = lowest_monthly
            (hold the line — don't grow further than the floor)

        Standard mode (daily_peaks_averaged == 1):
            Target = max(daily_peak, lowest_monthly)
        """
        lowest_monthly = min(self.monthly_peaks)
        # Stamp the current interval slot so _update_target's guard resets correctly
        now_stamp = dt_util.now()
        interval = self.interval_minutes
        if interval >= 60:
            current_slot = now_stamp.hour // (interval // 60)
        else:
            current_slot = now_stamp.hour * (60 // interval) + now_stamp.minute // interval
        self.last_target_update_hour = current_slot

        if self.only_one_peak_per_day and self.daily_peaks_averaged > 1:
            n = self.daily_peaks_averaged
            sub = self.daily_sub_peaks  # always length n, unfilled slots = reset_value
            R = lowest_monthly

            # daily_peak is the live committed average (from get_live_daily_peak)
            live_daily = self.get_live_daily_peak()

            # Filled sub-peaks = slots that have received real readings (> reset_value)
            filled = [s for s in sub if s > self.reset_value]
            min_filled = min(filled) if filled else self.reset_value

            any_sub_gte_floor = any(s >= R for s in sub)

            if not any_sub_gte_floor:
                # Case A: no sub-peak reaches the monthly floor yet
                new_target = R
            elif live_daily < R:
                # Case B: some sub-peaks >= floor but the daily average hasn't reached it
                # Find smallest X that makes the new daily average exactly = R
                top_n_minus_1 = sorted(sub, reverse=True)[:n - 1]
                T = n * R - sum(top_n_minus_1)
                # Headroom is the absolute ceiling: the highest this interval can be
                # without pushing the monthly average above R.
                # headroom = max(T, min(sub)) — same formula as get_immediate_headroom()
                headroom = max(T, min(sub))
                # Target = largest of [smallest filled sub-peak, threshold T],
                # but never above headroom (target is a "safe high", headroom is the true ceiling).
                new_target = min(max(min_filled, T), headroom)
            else:
                # Case C: daily average already at or above the monthly floor.
                # Target = min(sub) — the smallest value in any slot, including unfilled
                # slots that still hold reset_value.
                #
                # Using min_filled (ignoring reset_value slots) was wrong: if only one
                # of N sub-peak slots has committed a real reading, min_filled equals that
                # single committed value (e.g. 900 W), making target jump to 900 W even
                # though the remaining open slot can still bring the daily average down.
                # min(sub) correctly reflects that the open slot is still "in play" and
                # the target should not rise above the lowest value currently in the list.
                #
                # When all slots are filled with real readings, min(sub) == min_filled,
                # so the fix has no effect on that (correct) case.
                new_target = min(sub)

        else:
            new_target = max(self.daily_peak, lowest_monthly)

        if new_target != self.cached_target:
            self.cached_target = new_target
            self.last_updated["target"] = dt_util.now()
        else:
            self.cached_target = new_target
        _LOGGER.debug(
            "Target updated to %.1f Wh (lowest_monthly=%.1f)",
            self.cached_target, lowest_monthly,
        )

    def get_immediate_headroom(self) -> float | None:
        """Return the maximum this-interval consumption without increasing the monthly fee.

        Only meaningful in averaging mode (only_one_peak_per_day + daily_peaks_averaged > 1).
        Returns None otherwise.

        The headroom H is the highest value the current interval can reach such that
        the updated daily average (top-N including H) does not exceed lowest_monthly.

        Formula: H = N * lowest_monthly − sum(top_{N-1} largest committed sub-peaks)
        Clamped below by smallest_sub_peak (cannot do better than the weakest slot).

        If the result would be negative (impossible — sub-peaks already blow the budget)
        we return smallest_sub_peak as a conservative floor.
        """
        if not (self.only_one_peak_per_day and self.daily_peaks_averaged > 1):
            return None
        if not self.is_tariff_active():
            return None

        n = self.daily_peaks_averaged
        sub = self.daily_sub_peaks
        lowest_monthly = min(self.monthly_peaks)
        smallest_sub = min(sub)

        # Top (N-1) largest committed sub-peaks (the ones we cannot displace)
        top_n_minus_1 = sorted(sub, reverse=True)[:n - 1]
        H = n * lowest_monthly - sum(top_n_minus_1)

        # Clamp: never return less than the weakest sub-peak
        return max(H, smallest_sub)

    def get_safe_headroom(self) -> float | None:
        """Return the consumption level that will not worsen the rest-of-day position.

        Only meaningful in averaging mode (only_one_peak_per_day + daily_peaks_averaged > 1).
        Returns None otherwise.

        Safe headroom is the consumption ceiling for any single interval such that
        no sub-peak slot can be made *worse* for the remainder of the day — i.e. the
        value that, if never exceeded, guarantees the daily average cannot increase
        beyond its current committed value.

        In practice this equals the smallest committed sub-peak: as long as each
        remaining interval stays below min(sub_peaks), the average of the top-N
        sub-peaks can only stay the same or improve (a smaller slot gets replaced
        by an equally-small one, leaving the top-N unchanged).

        Unlike Immediate Headroom (which shows the *maximum* you can consume before
        the monthly average worsens), Safe Headroom shows the *safe floor* — the
        value you can always consume without any risk of a worse outcome.  It is
        most useful for advanced automation strategies that need a guaranteed-safe
        operating point, especially early in the day before sub-peak slots are filled.
        """
        if not (self.only_one_peak_per_day and self.daily_peaks_averaged > 1):
            return None
        if not self.is_tariff_active():
            return None

        sub = self.daily_sub_peaks
        if not sub:
            return None

        return min(sub)


    def get_estimated_consumption(self) -> float | None:
        """Get the estimated consumption (external sensor or internal).

        Returns None until the first real sensor reading has been processed
        after startup, preventing transient low values from propagating to
        downstream sensors (relative-to-target, cost increase).
        Also returns None when the internal estimation is flagged as unreliable
        (e.g. right after a restart when we have no samples yet and no
        previous_hour_rate to blend from).
        """
        if not self.has_received_reading:
            return None

        if self.estimation_sensor:
            state = self.hass.states.get(self.estimation_sensor)
            if state and state.state not in ("unknown", "unavailable", None):
                try:
                    value = float(state.state)
                    # External estimation sensors report in their own unit.
                    # All internal values are in Wh, so convert if needed.
                    unit = state.attributes.get("unit_of_measurement", "")
                    if unit in ("kWh", "kW"):
                        value = value * 1000.0
                    return value
                except (ValueError, TypeError):
                    pass

        # Internal estimation — return None when flagged unreliable
        if self._estimation_unreliable:
            return None

        # Internal estimation
        if hasattr(self, 'estimation_history') and self.estimation_history:
            return self.estimation_history[-1]

        return None

    def get_adjusted_estimated_consumption(self) -> float | None:
        """Get the estimated consumption adjusted for the current tariff state.

        In reduced tariff mode the reduction factor is applied so the result
        is in the same Wh space as cached_target (i.e. the value that would
        actually be recorded as a peak). Use this for relative-to-target and
        percentage-of-target calculations.

        Returns None when no estimate is available.
        """
        estimated = self.get_estimated_consumption()
        if estimated is None:
            return None
        if self.get_tariff_active_state() == ACTIVE_STATE_REDUCED and self.reduced_factor > 0:
            return estimated * self.reduced_factor
        return estimated

    def get_internal_estimation(self) -> float | None:
        """Get the internal estimation value (for the internal estimation sensor).
        
        Returns the MAX of:
        - The calculated prediction
        - The current hour consumption so far
        
        This prevents unrealistic predictions where estimate < actual consumption.
        """
        if not hasattr(self, 'estimation_history') or not self.estimation_history:
            return None
        
        predicted = self.estimation_history[-1]
        
        # Safeguard: never predict lower than what we've already consumed this hour
        actual_so_far = self.hour_cumulative_consumption
        
        return max(predicted, actual_so_far)

    def get_estimated_cost_increase(self) -> float | None:
        """Calculate estimated monthly cost increase above what the target already implies.

        Returns None when no estimate is available (startup, hour boundary) so the
        sensor shows unavailable rather than a misleading 0.

        If estimated ≤ target → 0.0 (no impact beyond what target already costs).
        Otherwise: (new_avg − target_avg) / 1000 × price_per_kw

        In averaging mode (daily_peaks_averaged > 1):
            Uses the estimation sensor (projected end-of-hour), but only if the
            estimate is larger than the smallest committed sub-peak.  This ensures
            the cost increase sensor only lights up when the current hour could
            actually displace a sub-peak slot.

        The reduction factor is applied to the estimate when in reduced tariff mode.
        """
        estimated = self.get_estimated_consumption()
        if estimated is None:
            return None

        # Apply reduction factor if currently in reduced tariff mode
        if self.get_tariff_active_state() == ACTIVE_STATE_REDUCED and self.reduced_factor > 0:
            adjusted_estimated = estimated * self.reduced_factor
        else:
            adjusted_estimated = estimated

        base_target = self.cached_target

        # If estimate doesn't exceed the target, no additional cost impact
        if adjusted_estimated <= base_target:
            return 0.0

        if self.only_one_peak_per_day and self.daily_peaks_averaged > 1:
            # Averaging mode: use estimation sensor for projected end-of-hour,
            # but only when it exceeds the weakest committed sub-peak
            n = self.daily_peaks_averaged
            if adjusted_estimated <= min(self.daily_sub_peaks):
                return 0.0  # won't displace any sub-peak, no cost impact

            # target scenario: current hour ends at exactly base_target
            t_candidates = sorted(self.daily_sub_peaks + [base_target], reverse=True)
            today_at_target = sum(t_candidates[:n]) / n

            # estimate scenario: current hour ends at projected adjusted_estimated
            e_candidates = sorted(self.daily_sub_peaks + [adjusted_estimated], reverse=True)
            today_at_estimate = sum(e_candidates[:n]) / n

            # monthly impact
            target_peaks = sorted(self.monthly_peaks + [today_at_target], reverse=True)[:self.number_of_peaks]
            target_avg_wh = sum(target_peaks) / len(target_peaks)

            new_peaks = sorted(self.monthly_peaks + [today_at_estimate], reverse=True)[:self.number_of_peaks]
            new_avg_wh = sum(new_peaks) / len(new_peaks)
        else:
            # Standard mode: the day's contribution is the single estimate value
            # target_avg: what the month would cost if today ends at exactly target
            target_peaks = sorted(self.monthly_peaks + [base_target], reverse=True)[:self.number_of_peaks]
            target_avg_wh = sum(target_peaks) / len(target_peaks)

            # new_avg: what the month would cost if today ends at the estimate
            new_peaks = sorted(self.monthly_peaks + [adjusted_estimated], reverse=True)[:self.number_of_peaks]
            new_avg_wh = sum(new_peaks) / len(new_peaks)

        increase = (new_avg_wh - target_avg_wh) / 1000.0 * self.price_per_kw
        return round(max(0.0, increase), 2)

    def get_linear_deviation(self) -> float | None:
        """Return how far the actual consumption is from ideal linear usage so far.

        The "ideal" model assumes that consumption should be distributed perfectly
        evenly across the interval.  At any point during the interval the ideal
        consumption so far is:

            ideal_wh = target_wh × (elapsed_seconds / interval_seconds)

        The deviation is:

            deviation_wh = hour_cumulative_consumption − ideal_wh

        A positive value means you are above the ideal pace (consuming too fast).
        A negative value means you are below the ideal pace (room to spare).

        Returns None when:
          - the target is zero / tariff inactive (sensor goes unavailable)
          - the consumption sensor has not yet produced a reading this interval
        """
        target_wh = self.get_target_consumption()
        if not target_wh:
            return None
        if not self.has_received_reading:
            return None

        now = dt_util.now()
        interval = self.interval_minutes
        interval_seconds = interval * 60

        # Compute elapsed seconds since the start of the current interval slot
        if interval >= 60:
            step_hours = interval // 60
            slot_hour = (now.hour // step_hours) * step_hours
            interval_start = now.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
        else:
            slot_minute = (now.minute // interval) * interval
            interval_start = now.replace(minute=slot_minute, second=0, microsecond=0)

        elapsed = (now - interval_start).total_seconds()
        # Clamp to [0, interval_seconds] to handle clock skew / boundary edge cases
        elapsed = max(0.0, min(elapsed, float(interval_seconds)))

        # Avoid division by zero right at the interval boundary
        if interval_seconds == 0:
            return None

        ideal_wh = target_wh * (elapsed / interval_seconds)
        return self.hour_cumulative_consumption - ideal_wh
