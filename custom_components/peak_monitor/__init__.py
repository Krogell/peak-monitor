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
    DEFAULT_FIXED_MONTHLY_FEE,
    DEFAULT_ONLY_ONE_PEAK_PER_DAY,
    DEFAULT_NUMBER_OF_PEAKS,
    DEFAULT_PRICE_PER_KW,
    DEFAULT_REDUCED_ALSO_ON_WEEKENDS,
    DEFAULT_REDUCED_END_HOUR,
    DEFAULT_REDUCED_FACTOR,
    DEFAULT_REDUCED_START_HOUR,
    DEFAULT_RESET_VALUE,
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

    return True


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

        # Cumulative sensor tracking (only active when sensor_resets_every_hour is False)
        self.last_cumulative_value: float | None = None
        self.last_seen_cumulative_value: float | None = None

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

        # Input unit — convert kWh input to Wh internally
        self.input_unit = data.get("input_unit", "Wh")
        
        # Output unit — display sensors in W or kW
        self.output_unit = data.get("output_unit", "W")

        # Whether the consumption sensor resets every hour (True) or is
        # cumulative / ever-increasing (False).
        self.sensor_resets_every_hour = get_bool(data, "sensor_resets_every_hour", DEFAULT_SENSOR_RESETS_EVERY_HOUR)

        # Only one peak per day mode (inverted: True = normal mode, False = multiple peaks mode)
        self.only_one_peak_per_day = get_bool(data, "only_one_peak_per_day", DEFAULT_ONLY_ONE_PEAK_PER_DAY)

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
            self.daily_peak = stored_data.get("daily_peak", self.reset_value)
            self.monthly_peaks = stored_data.get("monthly_peaks",
                                                 [self.reset_value] * self.number_of_peaks)
            self.last_month = stored_data.get("last_month")
            self.last_day = stored_data.get("last_day")
            self.last_cumulative_value = stored_data.get("last_cumulative_value")

            # Restore last_updated timestamps (stored as unix timestamps)
            for key in ("daily_peak", "monthly_peaks", "target"):
                stored_ts = stored_data.get(f"last_updated_{key}")
                if stored_ts is not None:
                    self.last_updated[key] = datetime.fromtimestamp(
                        stored_ts, tz=dt_util.now().tzinfo
                    )
            self.last_seen_cumulative_value = self.last_cumulative_value
            
            # Restore hour_cumulative_consumption only if from current hour
            # AND we're not at the hourly boundary (first 2 minutes of the hour)
            stored_timestamp = stored_data.get("hour_cumulative_timestamp")
            if stored_timestamp:
                now = dt_util.now()
                stored_time = datetime.fromtimestamp(stored_timestamp, tz=now.tzinfo)
                same_hour = (stored_time.hour == now.hour and stored_time.day == now.day)

                if not self.only_one_peak_per_day:
                    # Multiple-peaks mode: daily_peak is committed at every hour boundary.
                    # If the stored timestamp is from a previous hour, HA was offline over
                    # that boundary — commit the stored daily_peak now so it isn't lost,
                    # then reset daily_peak for the current hour.
                    if not same_hour and self.daily_peak > min(self.monthly_peaks):
                        peaks = self.monthly_peaks + [self.daily_peak]
                        peaks.sort(reverse=True)
                        self.monthly_peaks = peaks[:self.number_of_peaks]
                        _LOGGER.info(
                            "Startup catch-up: committed missed hourly peak %s Wh "
                            "from %s to monthly peaks: %s",
                            round(self.daily_peak),
                            stored_time.strftime("%H:%M"),
                            self.monthly_peaks,
                        )
                    self.daily_peak = self.reset_value

                # Restore hour_cumulative_consumption only if from current hour
                # and not at the very start of the hour (avoid stale data)
                if same_hour and now.minute >= 2:
                    self.hour_cumulative_consumption = stored_data.get("hour_cumulative_consumption", 0.0)
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
                if not self.sensor_resets_every_hour and self.last_cumulative_value is not None:
                    if not same_hour:
                        self._restart_rebaseline_needed = True
                    # same_hour: keep _restart_rebaseline_needed = False (default)

            # Always restore previous_hour_rate — it's valid across restarts
            # and gives the estimation blending formula a meaningful fallback
            stored_rate = stored_data.get("previous_hour_rate")
            if stored_rate is not None:
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
        """
        now = dt_util.now()

        if self.last_month is not None and self.last_month != now.month:
            # Month changed while HA was off.
            # Commit the stored daily peak (from last month's last day) to that
            # month's peaks before wiping everything — but only in normal mode.
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
            # Commit the stored daily peak in normal mode.
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
        """Schedule next hourly update at local hour boundary."""
        if self._unsub_hourly:
            self._unsub_hourly()
        
        now = dt_util.now()
        
        # Calculate next local hour boundary
        next_hour = now.replace(minute=0, second=0, microsecond=0)
        if next_hour <= now:
            next_hour = next_hour + timedelta(hours=1)
        
        _LOGGER.debug(
            "Scheduling next hourly update at %s (local time, timezone: %s)",
            next_hour.strftime("%Y-%m-%d %H:%M:%S %Z"),
            next_hour.tzinfo
        )
        
        self._unsub_hourly = async_track_point_in_time(
            self.hass, self._async_update_hourly_and_reschedule, next_hour
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

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    async def _async_save_data(self) -> None:
        """Save persistent data to storage."""
        now = dt_util.now()
        data = {
            "daily_peak": self.daily_peak,
            "monthly_peaks": self.monthly_peaks,
            "last_month": now.month,
            "last_day": now.day,
            "last_cumulative_value": self.last_cumulative_value,
            "hour_cumulative_consumption": self.hour_cumulative_consumption,
            "hour_cumulative_timestamp": now.timestamp(),
            "previous_hour_rate": self.previous_hour_rate,
        }
        # Persist last_updated timestamps for sensors that survive restarts
        for key in ("daily_peak", "monthly_peaks", "target"):
            ts = self.last_updated.get(key)
            if ts is not None:
                data[f"last_updated_{key}"] = ts.timestamp()
        await self.store.async_save(data)

    # ------------------------------------------------------------------
    # Unit conversion helper
    # ------------------------------------------------------------------

    def _convert_to_wh(self, value: float) -> float:
        """Convert an input sensor value to Wh based on configured input_unit."""
        if self.input_unit == "kWh":
            return value * 1000.0
        return value
    
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
            # Mark consumption sensor as unavailable
            self.consumption_sensor_available = False
            await self._async_notify_listeners()
            return

        # Mark consumption sensor as available
        if not self.consumption_sensor_available:
            _LOGGER.info(
                "Consumption sensor '%s' is now available again",
                self.consumption_sensor
            )
            self.consumption_sensor_available = True

        # Warn once if the sensor's reported unit is unexpected
        if not self._input_unit_warned:
            attrs = getattr(new_state, "attributes", None) or {}
            unit = attrs.get("unit_of_measurement")
            check_input_sensor_unit(self.consumption_sensor, unit, _LOGGER)
            self._input_unit_warned = True

        try:
            raw_value = self._convert_to_wh(float(new_state.state))
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Failed to parse consumption sensor '%s' value '%s': %s",
                self.consumption_sensor, new_state.state, err
            )
            return

        # --- Determine consumption_this_hour (always needed for estimation) ---
        if self.sensor_resets_every_hour:
            # Sensor resets each hour: the value IS consumption this hour
            consumption_this_hour = raw_value
        else:
            # Cumulative sensor: consumption = current - hour-start baseline
            if self.last_cumulative_value is None:
                # No baseline yet — seed it and skip
                self.last_cumulative_value = raw_value
                self.last_seen_cumulative_value = raw_value
                await self._async_save_data()
                return

            # After a cross-hour restart, re-baseline from the current raw reading
            # so that hour_cumulative_consumption starts fresh at 0 for the new hour.
            if self._restart_rebaseline_needed:
                _LOGGER.info(
                    "Restart rebaseline (cross-hour): resetting cumulative baseline "
                    "from %s to %s Wh; hour consumption starts at 0",
                    self.last_cumulative_value, raw_value
                )
                self.last_cumulative_value = raw_value
                self.last_seen_cumulative_value = raw_value
                self.hour_cumulative_consumption = 0.0
                self._restart_rebaseline_needed = False
                await self._async_save_data()
                await self._async_notify_listeners()
                return

            consumption_this_hour = raw_value - self.last_cumulative_value

            if consumption_this_hour < 0:
                # Sensor reset (e.g. new month) — re-baseline and skip
                _LOGGER.info(
                    "Cumulative sensor reset detected (was %s, now %s). Re-baselining.",
                    self.last_cumulative_value, raw_value
                )
                self.last_cumulative_value = raw_value
                self.last_seen_cumulative_value = raw_value
                self.hour_cumulative_consumption = 0.0
                await self._async_save_data()
                await self._async_notify_listeners()
                return

            self.last_seen_cumulative_value = raw_value

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
            
            # Calculate internal estimation
            estimated = calculate_internal_estimation(
                self.consumption_samples,
                now,
                previous_hour_rate=self.previous_hour_rate,
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
        if adjusted_consumption > (self.daily_peak + PEAK_UPDATE_EPSILON):
            old_peak = self.daily_peak
            self.daily_peak = adjusted_consumption
            self.last_updated["daily_peak"] = dt_util.now()
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
        """Update on the hour."""
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

            # Determine the tariff state for the hour that just ended.
            # The hourly callback fires at :00 (start of new hour), so we check
            # one minute before the trigger time to get the state of the ending hour.
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
        self.last_updated["hour_consumption"] = dt_util.now()

        # --- Immediately recompute estimation for the new hour ---
        # calculate_internal_estimation with empty samples + previous_hour_rate
        # returns rate * 3600, which is the best guess at :00:00 before any new
        # readings arrive. This prevents downstream sensors (relative, percentage,
        # cost increase) from showing stale values from the ended hour.
        if not self.estimation_sensor:
            boundary_estimate = calculate_internal_estimation(
                [],  # no samples yet in the new hour
                now,
                previous_hour_rate=self.previous_hour_rate,
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
            peaks = self.monthly_peaks + [self.daily_peak]
            peaks.sort(reverse=True)
            self.monthly_peaks = peaks[:self.number_of_peaks]
            self.last_updated["monthly_peaks"] = dt_util.now()

            _LOGGER.info("Committed daily peak %s Wh to monthly peaks: %s",
                         self.daily_peak, self.monthly_peaks)
        
        # SECOND: Check if we need to do a monthly reset
        should_reset_monthly = False
        
        # Check real monthly reset (month changed)
        if self.last_month is not None and self.last_month != now.month:
            should_reset_monthly = True
            _LOGGER.info("Monthly reset triggered: month changed from %s to %s", 
                        self.last_month, now.month)
        
        # THIRD: If monthly reset is needed, reset monthly peaks AND daily peak
        if should_reset_monthly:
            # Perform monthly reset - this also resets daily peak
            self.monthly_peaks = [self.reset_value] * self.number_of_peaks
            self.daily_peak = self.reset_value
            self.last_month = now.month
            _LOGGER.info("Reset monthly peaks AND daily peak to %s Wh", self.reset_value)
        else:
            # No monthly reset, just reset daily peak
            self.daily_peak = self.reset_value
            _LOGGER.info("Reset daily peak to %s Wh", self.reset_value)

        # Update tracking
        self.last_day = now.day
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
        """Calculate the current tariff (average of top N peaks).

        If include_today is True and today's peak would change the average,
        it is included for a real-time view.
        """
        if include_today and self.daily_peak > min(self.monthly_peaks):
            peaks = sorted(self.monthly_peaks + [self.daily_peak], reverse=True)
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

        This mirrors the include_today logic in get_current_tariff: daily_peak is
        included in the live average whenever it would displace the current minimum.
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
        """Update cached target if the hour has changed (hourly boundary call)."""
        now = dt_util.now()
        if self.last_target_update_hour == now.hour:
            return
        self._force_update_target()

    def _force_update_target(self) -> None:
        """Unconditionally recalculate and cache the base target.

        Called on startup, midnight reset, peak change, and manual reset.
        """
        now = dt_util.now()
        
        # On restart: only update if we haven't updated this hour yet
        # This prevents unnecessary target recalculation when HA restarts mid-hour
        if (hasattr(self, '_is_startup') and self._is_startup and 
            self.last_target_update_hour == now.hour):
            _LOGGER.debug("Skipping target update on startup - already updated this hour")
            return
        
        self.last_target_update_hour = now.hour

        lowest_monthly = min(self.monthly_peaks)
        new_target = max(self.daily_peak, lowest_monthly)
        if new_target != self.cached_target:
            self.cached_target = new_target
            self.last_updated["target"] = dt_util.now()
        else:
            self.cached_target = new_target
        _LOGGER.debug("Target updated to %s Wh (daily: %s, lowest monthly: %s)",
                      self.cached_target, self.daily_peak, lowest_monthly)

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
                    return float(state.state)
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

        Where:
            target_avg = mean of top N from (monthly_peaks + [target])
            new_avg    = mean of top N from (monthly_peaks + [adjusted_estimated])

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

        # target_avg: what the month would cost if today ends at exactly target
        target_peaks = sorted(self.monthly_peaks + [base_target], reverse=True)[:self.number_of_peaks]
        target_avg_wh = sum(target_peaks) / len(target_peaks)

        # new_avg: what the month would cost if today ends at the estimate
        new_peaks = sorted(self.monthly_peaks + [adjusted_estimated], reverse=True)[:self.number_of_peaks]
        new_avg_wh = sum(new_peaks) / len(new_peaks)

        increase = (new_avg_wh - target_avg_wh) / 1000.0 * self.price_per_kw
        return round(max(0.0, increase), 2)
