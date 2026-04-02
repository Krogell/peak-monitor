"""Config flow for Peak Monitor integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_CONSUMPTION_SENSOR,
    CONF_ESTIMATION_SENSOR,
    CONF_EXTERNAL_MUTE_SENSOR,
    CONF_EXTERNAL_REDUCED_SENSOR,
    CONF_PRICE_PER_KW,
    CONF_FIXED_MONTHLY_FEE,
    CONF_ACTIVE_START_HOUR,
    CONF_ACTIVE_END_HOUR,
    CONF_ACTIVE_MONTHS,
    CONF_NUMBER_OF_PEAKS,
    CONF_ONLY_ONE_PEAK_PER_DAY,
    CONF_DAILY_PEAKS_AVERAGED,
    CONF_HOLIDAYS,
    CONF_HOLIDAY_BEHAVIOR,
    CONF_WEEKEND_BEHAVIOR,
    CONF_WEEKEND_START_HOUR,
    CONF_WEEKEND_END_HOUR,
    CONF_RESET_VALUE,
    CONF_RESET_INTERVAL,
    CONF_INTERVAL_MINUTES,
    CONF_SENSOR_RESETS_EVERY_HOUR,
    CONF_INPUT_UNIT,
    CONF_OUTPUT_UNIT,
    CONF_CURRENCY,
    CONF_DAILY_REDUCED_TARIFF_ENABLED,
    CONF_REDUCED_START_HOUR,
    CONF_REDUCED_END_HOUR,
    CONF_REDUCED_FACTOR,
    CONF_REDUCED_ALSO_ON_WEEKENDS,
    DEFAULT_PRICE_PER_KW,
    DEFAULT_FIXED_MONTHLY_FEE,
    DEFAULT_ACTIVE_START_HOUR,
    DEFAULT_ACTIVE_END_HOUR,
    DEFAULT_ACTIVE_MONTHS,
    DEFAULT_NUMBER_OF_PEAKS,
    DEFAULT_ONLY_ONE_PEAK_PER_DAY,
    DEFAULT_DAILY_PEAKS_AVERAGED,
    DEFAULT_HOLIDAYS,
    DEFAULT_HOLIDAY_BEHAVIOR,
    DEFAULT_WEEKEND_BEHAVIOR,
    DEFAULT_WEEKEND_START_HOUR,
    DEFAULT_WEEKEND_END_HOUR,
    DEFAULT_RESET_VALUE,
    DEFAULT_RESET_INTERVAL,
    DEFAULT_INTERVAL_MINUTES,
    DEFAULT_SENSOR_RESETS_EVERY_HOUR,
    DEFAULT_INPUT_UNIT,
    DEFAULT_OUTPUT_UNIT,
    DEFAULT_CURRENCY,
    DEFAULT_DAILY_REDUCED_TARIFF_ENABLED,
    DEFAULT_REDUCED_START_HOUR,
    DEFAULT_REDUCED_END_HOUR,
    DEFAULT_REDUCED_FACTOR,
    DEFAULT_REDUCED_ALSO_ON_WEEKENDS,
    MONTH_OPTIONS,
    HOLIDAY_OPTIONS,
    HOLIDAY_BEHAVIOR_OPTIONS,
    WEEKEND_BEHAVIOR_OPTIONS,
    INPUT_UNIT_OPTIONS,
    INPUT_UNIT_AUTO,
    OUTPUT_UNIT_OPTIONS,
    RESET_INTERVAL_OPTIONS,
    INTERVAL_OPTIONS,
    CURRENCY_OPTIONS,
    CURRENCY_CUSTOM,
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input.

    Returns:
        Dictionary with 'title' on success, or 'error' key on failure.
    """
    consumption_state = hass.states.get(data[CONF_CONSUMPTION_SENSOR])
    if not consumption_state:
        return {"error": "consumption_sensor_not_found"}

    # ---------------------------------------------------------------
    # Unit resolution: auto-detect vs manual override
    # ---------------------------------------------------------------
    sensor_unit = consumption_state.attributes.get("unit_of_measurement", "")

    _HA_UNIT_MAP = {
        "kWh": "kWh", "kilowatt_hour": "kWh",
        "kW": "kW",   "kilowatt": "kW",
        "Wh": "Wh",   "watt_hour": "Wh",
        "W": "W",     "watt": "W",
    }
    detected_unit = _HA_UNIT_MAP.get(sensor_unit)  # None if sensor has no/unknown unit

    # "" means "auto" (the new blank/default option); anything else is an explicit choice
    _raw_unit = data.get(CONF_INPUT_UNIT, INPUT_UNIT_AUTO) or INPUT_UNIT_AUTO
    # Normalise legacy "" (old "auto" sentinel) to the current "auto" value
    manual_unit = INPUT_UNIT_AUTO if _raw_unit == "" else _raw_unit

    warnings: list[dict] = []  # collected config warnings to fire as persistent notifications

    if detected_unit and manual_unit and manual_unit != detected_unit:
        # Both present but conflicting — autodetect wins, warn the user
        warnings.append({
            "key": "unit_conflict",
            "detected": detected_unit,
            "manual": manual_unit,
        })
        data[CONF_INPUT_UNIT] = detected_unit

    elif detected_unit:
        # Auto-detect available — use it silently
        data[CONF_INPUT_UNIT] = detected_unit

    elif manual_unit:
        # No auto-detect, but user specified a unit — use it silently
        data[CONF_INPUT_UNIT] = manual_unit

    else:
        # Neither auto-detect nor manual — fall back to Wh and warn
        warnings.append({"key": "unit_unknown"})
        data[CONF_INPUT_UNIT] = DEFAULT_INPUT_UNIT

    # ---------------------------------------------------------------
    # Handle custom currency — validate against ISO 4217
    # ---------------------------------------------------------------
    currency = data.get(CONF_CURRENCY, DEFAULT_CURRENCY)
    custom_currency = data.pop("custom_currency", None)
    if currency == CURRENCY_CUSTOM:
        if custom_currency:
            from .const import ISO_4217_CURRENCIES
            if custom_currency.upper() not in ISO_4217_CURRENCIES:
                return {"error": "invalid_currency"}
            data[CONF_CURRENCY] = custom_currency.upper()
        else:
            data[CONF_CURRENCY] = DEFAULT_CURRENCY

    # ---------------------------------------------------------------
    # Validate and auto-correct implausible config combinations
    # ---------------------------------------------------------------
    only_one = data.get("only_one_peak_per_day", True)
    daily_avg = int(data.get("daily_peaks_averaged", 1))
    interval_min = int(data.get("interval_minutes", DEFAULT_INTERVAL_MINUTES))

    # Incompatible: averaging N sub-peaks per day requires only_one_peak_per_day
    if not only_one and daily_avg > 1:
        warnings.append({
            "key": "avg_incompatible_with_multi_peak",
            "daily_avg": daily_avg,
        })
        # Auto-correct: reset averaging to 1 (disabled)
        data["daily_peaks_averaged"] = 1

    # Sub-hour intervals with per-day averaging: each interval commits independently,
    # so the "daily sub-peak" slots fill up much faster than expected.
    if interval_min < 60 and daily_avg > 1:
        warnings.append({
            "key": "sub_hour_interval_with_averaging",
            "interval_min": interval_min,
            "daily_avg": daily_avg,
        })

    # ---------------------------------------------------------------
    # Validate optional sensor references
    # ---------------------------------------------------------------
    estimation_sensor = data.get(CONF_ESTIMATION_SENSOR)
    if estimation_sensor is not None:
        est_str = str(estimation_sensor).strip()
        if est_str and est_str.lower() != "none":
            if not hass.states.get(estimation_sensor):
                return {"error": "estimation_sensor_not_found"}

    return {"title": data.get(CONF_NAME, "Peak Monitor"), "warnings": warnings}


async def _async_fire_config_choice_warnings(
    hass: HomeAssistant,
    data: dict[str, Any],
    warnings: list[dict],
    entry_id: str | None = None,
) -> None:
    """Fire persistent notifications for incompatible config choices.

    Called after a successful config/reconfig flow submission — never on restart.
    Each notification is replaced (same ID) so reconfiguring to a still-incompatible
    state updates the message rather than stacking duplicates.
    """
    from homeassistant.components.persistent_notification import async_create, async_dismiss

    instance = data.get("name", "Peak Monitor")
    # Use entry_id when available (reconfigure/options); fall back to instance name
    # for initial setup where the entry doesn't exist yet.
    id_prefix = f"peak_monitor_{entry_id}" if entry_id else f"peak_monitor_{instance}"

    # Dismiss stale choice-warnings first so a fixed config clears them
    async_dismiss(hass, f"{id_prefix}_avg_incompatible")
    async_dismiss(hass, f"{id_prefix}_sub_hour_averaging")

    for warning in warnings:
        key = warning.get("key", "")

        if key == "avg_incompatible_with_multi_peak":
            daily_avg = warning.get("daily_avg", 2)
            async_create(
                hass,
                title=f"⚠️ Peak Monitor — Incompatible settings auto-corrected ({instance})",
                message=(
                    f"**Average of {daily_avg} highest peaks per day** requires "
                    f"**Only one peak per day** to be enabled, but it is currently disabled.\n\n"
                    f"**What happens:** Daily peak averaging has been disabled automatically "
                    f"(set to 1). The integration is running in standard "
                    f"*multiple peaks per day* mode.\n\n"
                    f"To use averaging, enable *Only one peak per day* in the main settings."
                ),
                notification_id=f"{id_prefix}_avg_incompatible",
            )

        elif key == "sub_hour_interval_with_averaging":
            interval_min = warning.get("interval_min", 30)
            daily_avg = warning.get("daily_avg", 2)
            async_create(
                hass,
                title=f"ℹ️ Peak Monitor — Sub-hour interval with daily averaging ({instance})",
                message=(
                    f"You have a **{interval_min}-minute interval** combined with "
                    f"**average of {daily_avg} highest peaks per day**.\n\n"
                    f"**What happens:** Each interval boundary (every {interval_min} min) "
                    f"commits a candidate to the daily sub-peak slots. With "
                    f"{60 // interval_min} intervals per hour, your {daily_avg} sub-peak "
                    f"slots may fill up within the first "
                    f"{daily_avg * interval_min} minutes of active tariff time.\n\n"
                    f"The expected behaviour of this combination is not fully defined. "
                    f"The integration will continue working, but results may not be what "
                    f"you expect. If you have a use case for this, please contact the "
                    f"developer."
                ),
                notification_id=f"{id_prefix}_sub_hour_averaging",
            )


def _get_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the config schema with collapsible sections.

    Args:
        defaults: Dictionary of default values to pre-populate.

    Returns:
        Voluptuous schema for configuration with sections.
    """
    if defaults is None:
        defaults = {}

    return vol.Schema({
        vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, "Peak Monitor")): str,

        # ========== Basic setup ==========
        vol.Required("basic_setup_section"): section(
            vol.Schema({
                vol.Required(
                    CONF_CONSUMPTION_SENSOR,
                    default=defaults.get(CONF_CONSUMPTION_SENSOR)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class=["energy", "power"]
                    )
                ),
                vol.Optional(
                    CONF_SENSOR_RESETS_EVERY_HOUR,
                    default=defaults.get(CONF_SENSOR_RESETS_EVERY_HOUR, DEFAULT_SENSOR_RESETS_EVERY_HOUR)
                ): bool,
                vol.Optional(
                    CONF_NUMBER_OF_PEAKS,
                    default=str(defaults.get(CONF_NUMBER_OF_PEAKS, DEFAULT_NUMBER_OF_PEAKS))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(1, 11)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_ONLY_ONE_PEAK_PER_DAY,
                    default=defaults.get(CONF_ONLY_ONE_PEAK_PER_DAY, DEFAULT_ONLY_ONE_PEAK_PER_DAY)
                ): bool,
                vol.Optional(
                    CONF_DAILY_PEAKS_AVERAGED,
                    default=str(defaults.get(CONF_DAILY_PEAKS_AVERAGED, DEFAULT_DAILY_PEAKS_AVERAGED))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(1, 6)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_PRICE_PER_KW,
                    default=defaults.get(CONF_PRICE_PER_KW, DEFAULT_PRICE_PER_KW)
                ): vol.All(
                    vol.Coerce(float), vol.Range(min=0)
                ),
                vol.Optional(
                    CONF_FIXED_MONTHLY_FEE,
                    default=defaults.get(CONF_FIXED_MONTHLY_FEE, DEFAULT_FIXED_MONTHLY_FEE)
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_ACTIVE_MONTHS,
                    default=defaults.get(CONF_ACTIVE_MONTHS, DEFAULT_ACTIVE_MONTHS)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=MONTH_OPTIONS,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="months",
                    )
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Weekdays ==========
        vol.Required("weekdays_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_ACTIVE_START_HOUR,
                    default=str(defaults.get(CONF_ACTIVE_START_HOUR, DEFAULT_ACTIVE_START_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_ACTIVE_END_HOUR,
                    default=str(defaults.get(CONF_ACTIVE_END_HOUR, DEFAULT_ACTIVE_END_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Weekends ==========
        vol.Required("weekends_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_WEEKEND_BEHAVIOR,
                    default=defaults.get(CONF_WEEKEND_BEHAVIOR, DEFAULT_WEEKEND_BEHAVIOR)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WEEKEND_BEHAVIOR_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="weekend_behavior",
                    )
                ),
                vol.Optional(
                    CONF_WEEKEND_START_HOUR,
                    default=str(defaults.get(CONF_WEEKEND_START_HOUR, DEFAULT_WEEKEND_START_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_WEEKEND_END_HOUR,
                    default=str(defaults.get(CONF_WEEKEND_END_HOUR, DEFAULT_WEEKEND_END_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Holidays ==========
        vol.Required("holidays_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_HOLIDAY_BEHAVIOR,
                    default=defaults.get(CONF_HOLIDAY_BEHAVIOR, DEFAULT_HOLIDAY_BEHAVIOR)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HOLIDAY_BEHAVIOR_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="holiday_behavior",
                    )
                ),
                vol.Optional(
                    CONF_HOLIDAYS,
                    default=defaults.get(CONF_HOLIDAYS, DEFAULT_HOLIDAYS)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HOLIDAY_OPTIONS,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="holidays",
                    )
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Periodic Reduced Tariff ==========
        vol.Required("reduced_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_DAILY_REDUCED_TARIFF_ENABLED,
                    default=defaults.get(CONF_DAILY_REDUCED_TARIFF_ENABLED, DEFAULT_DAILY_REDUCED_TARIFF_ENABLED)
                ): bool,
                vol.Optional(
                    CONF_REDUCED_ALSO_ON_WEEKENDS,
                    default=defaults.get(CONF_REDUCED_ALSO_ON_WEEKENDS, DEFAULT_REDUCED_ALSO_ON_WEEKENDS)
                ): bool,
                vol.Optional(
                    CONF_REDUCED_START_HOUR,
                    default=str(defaults.get(CONF_REDUCED_START_HOUR, DEFAULT_REDUCED_START_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_REDUCED_END_HOUR,
                    default=str(defaults.get(CONF_REDUCED_END_HOUR, DEFAULT_REDUCED_END_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Optional External Sensors ==========
        vol.Required("external_sensors_section"): section(
            vol.Schema({
                vol.Optional(CONF_ESTIMATION_SENSOR, default=None): vol.Any(
                    None,
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="energy"
                        )
                    )
                ),
                vol.Optional(CONF_EXTERNAL_REDUCED_SENSOR, default=defaults.get(CONF_EXTERNAL_REDUCED_SENSOR)): vol.Any(
                    None,
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor")
                    )
                ),
                vol.Optional(CONF_EXTERNAL_MUTE_SENSOR, default=defaults.get(CONF_EXTERNAL_MUTE_SENSOR)): vol.Any(
                    None,
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor")
                    )
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Advanced ==========
        vol.Required("advanced_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_INPUT_UNIT,
                    default=defaults.get(CONF_INPUT_UNIT, INPUT_UNIT_AUTO)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=INPUT_UNIT_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="input_unit",
                    )
                ),
                vol.Optional(
                    CONF_REDUCED_FACTOR,
                    default=defaults.get(CONF_REDUCED_FACTOR, DEFAULT_REDUCED_FACTOR)
                ): vol.All(
                    vol.Coerce(float), vol.Range(min=0.01, max=1.0)
                ),
                vol.Optional(
                    CONF_RESET_VALUE,
                    default=defaults.get(CONF_RESET_VALUE, DEFAULT_RESET_VALUE)
                ): vol.All(
                    vol.Coerce(int), vol.Range(min=0)
                ),
                vol.Optional(
                    CONF_INTERVAL_MINUTES,
                    default=str(defaults.get(CONF_INTERVAL_MINUTES, DEFAULT_INTERVAL_MINUTES))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=INTERVAL_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="interval_minutes",
                    )
                ),
                vol.Optional(
                    CONF_RESET_INTERVAL,
                    default=defaults.get(CONF_RESET_INTERVAL, DEFAULT_RESET_INTERVAL)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=RESET_INTERVAL_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="reset_interval",
                    )
                ),
                vol.Optional(
                    CONF_OUTPUT_UNIT,
                    default=defaults.get(CONF_OUTPUT_UNIT, DEFAULT_OUTPUT_UNIT)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=OUTPUT_UNIT_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="output_unit",
                    )
                ),
                vol.Optional(
                    CONF_CURRENCY,
                    default=defaults.get(CONF_CURRENCY, DEFAULT_CURRENCY)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=CURRENCY_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="currency",
                    )
                ),
                vol.Optional("custom_currency", default=defaults.get("custom_currency", "")): str,
            }),
            {"collapsed": True}
        ),
    })


def _get_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return the options schema with safe defaults and sections."""
    return vol.Schema({
        # ========== Basic setup ==========
        vol.Required("basic_setup_section"): section(
            vol.Schema({
                vol.Required(
                    CONF_CONSUMPTION_SENSOR,
                    default=defaults.get(CONF_CONSUMPTION_SENSOR)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class=["energy", "power"]
                    )
                ),
                vol.Optional(
                    CONF_SENSOR_RESETS_EVERY_HOUR,
                    default=defaults.get(CONF_SENSOR_RESETS_EVERY_HOUR, DEFAULT_SENSOR_RESETS_EVERY_HOUR)
                ): bool,
                vol.Optional(
                    CONF_NUMBER_OF_PEAKS,
                    default=str(defaults.get(CONF_NUMBER_OF_PEAKS, DEFAULT_NUMBER_OF_PEAKS))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(1, 11)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_ONLY_ONE_PEAK_PER_DAY,
                    default=defaults.get(CONF_ONLY_ONE_PEAK_PER_DAY, DEFAULT_ONLY_ONE_PEAK_PER_DAY)
                ): bool,
                vol.Optional(
                    CONF_DAILY_PEAKS_AVERAGED,
                    default=str(defaults.get(CONF_DAILY_PEAKS_AVERAGED, DEFAULT_DAILY_PEAKS_AVERAGED))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(1, 6)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_PRICE_PER_KW,
                    default=defaults.get(CONF_PRICE_PER_KW, DEFAULT_PRICE_PER_KW)
                ): vol.All(
                    vol.Coerce(float), vol.Range(min=0)
                ),
                vol.Optional(
                    CONF_FIXED_MONTHLY_FEE,
                    default=defaults.get(CONF_FIXED_MONTHLY_FEE, DEFAULT_FIXED_MONTHLY_FEE)
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_ACTIVE_MONTHS,
                    default=defaults.get(CONF_ACTIVE_MONTHS, DEFAULT_ACTIVE_MONTHS)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=MONTH_OPTIONS,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="months",
                    )
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Weekdays ==========
        vol.Required("weekdays_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_ACTIVE_START_HOUR,
                    default=str(defaults.get(CONF_ACTIVE_START_HOUR, DEFAULT_ACTIVE_START_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_ACTIVE_END_HOUR,
                    default=str(defaults.get(CONF_ACTIVE_END_HOUR, DEFAULT_ACTIVE_END_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Weekends ==========
        vol.Required("weekends_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_WEEKEND_BEHAVIOR,
                    default=defaults.get(CONF_WEEKEND_BEHAVIOR, DEFAULT_WEEKEND_BEHAVIOR)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WEEKEND_BEHAVIOR_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="weekend_behavior",
                    )
                ),
                vol.Optional(
                    CONF_WEEKEND_START_HOUR,
                    default=str(defaults.get(CONF_WEEKEND_START_HOUR, DEFAULT_WEEKEND_START_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_WEEKEND_END_HOUR,
                    default=str(defaults.get(CONF_WEEKEND_END_HOUR, DEFAULT_WEEKEND_END_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Holidays ==========
        vol.Required("holidays_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_HOLIDAY_BEHAVIOR,
                    default=defaults.get(CONF_HOLIDAY_BEHAVIOR, DEFAULT_HOLIDAY_BEHAVIOR)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HOLIDAY_BEHAVIOR_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="holiday_behavior",
                    )
                ),
                vol.Optional(
                    CONF_HOLIDAYS,
                    default=defaults.get(CONF_HOLIDAYS, DEFAULT_HOLIDAYS)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HOLIDAY_OPTIONS,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="holidays",
                    )
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Periodic Reduced Tariff ==========
        vol.Required("reduced_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_DAILY_REDUCED_TARIFF_ENABLED,
                    default=defaults.get(CONF_DAILY_REDUCED_TARIFF_ENABLED, DEFAULT_DAILY_REDUCED_TARIFF_ENABLED)
                ): bool,
                vol.Optional(
                    CONF_REDUCED_ALSO_ON_WEEKENDS,
                    default=defaults.get(CONF_REDUCED_ALSO_ON_WEEKENDS, DEFAULT_REDUCED_ALSO_ON_WEEKENDS)
                ): bool,
                vol.Optional(
                    CONF_REDUCED_START_HOUR,
                    default=str(defaults.get(CONF_REDUCED_START_HOUR, DEFAULT_REDUCED_START_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
                vol.Optional(
                    CONF_REDUCED_END_HOUR,
                    default=str(defaults.get(CONF_REDUCED_END_HOUR, DEFAULT_REDUCED_END_HOUR))
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(i) for i in range(24)],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Coerce(int)
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Optional External Sensors ==========
        vol.Required("external_sensors_section"): section(
            vol.Schema({
                vol.Optional(CONF_ESTIMATION_SENSOR, default=defaults.get(CONF_ESTIMATION_SENSOR)): vol.Any(
                    None,
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="energy"
                        )
                    )
                ),
                vol.Optional(CONF_EXTERNAL_REDUCED_SENSOR, default=defaults.get(CONF_EXTERNAL_REDUCED_SENSOR)): vol.Any(
                    None,
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor")
                    )
                ),
                vol.Optional(CONF_EXTERNAL_MUTE_SENSOR, default=defaults.get(CONF_EXTERNAL_MUTE_SENSOR)): vol.Any(
                    None,
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor")
                    )
                ),
            }),
            {"collapsed": True}
        ),

        # ========== Advanced ==========
        vol.Required("advanced_section"): section(
            vol.Schema({
                vol.Optional(
                    CONF_INPUT_UNIT,
                    default=defaults.get(CONF_INPUT_UNIT, INPUT_UNIT_AUTO)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=INPUT_UNIT_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="input_unit",
                    )
                ),
                vol.Optional(
                    CONF_REDUCED_FACTOR,
                    default=defaults.get(CONF_REDUCED_FACTOR, DEFAULT_REDUCED_FACTOR)
                ): vol.All(
                    vol.Coerce(float), vol.Range(min=0.01, max=1.0)
                ),
                vol.Optional(
                    CONF_RESET_VALUE,
                    default=defaults.get(CONF_RESET_VALUE, DEFAULT_RESET_VALUE)
                ): vol.All(
                    vol.Coerce(int), vol.Range(min=0)
                ),
                vol.Optional(
                    CONF_INTERVAL_MINUTES,
                    default=str(defaults.get(CONF_INTERVAL_MINUTES, DEFAULT_INTERVAL_MINUTES))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=INTERVAL_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="interval_minutes",
                    )
                ),
                vol.Optional(
                    CONF_RESET_INTERVAL,
                    default=defaults.get(CONF_RESET_INTERVAL, DEFAULT_RESET_INTERVAL)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=RESET_INTERVAL_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="reset_interval",
                    )
                ),
                vol.Optional(
                    CONF_OUTPUT_UNIT,
                    default=defaults.get(CONF_OUTPUT_UNIT, DEFAULT_OUTPUT_UNIT)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=OUTPUT_UNIT_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="output_unit",
                    )
                ),
                vol.Optional(
                    CONF_CURRENCY,
                    default=defaults.get(CONF_CURRENCY, DEFAULT_CURRENCY)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=CURRENCY_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="currency",
                    )
                ),
                vol.Optional("custom_currency", default=defaults.get("custom_currency", "")): str,
            }),
            {"collapsed": True}
        ),
    })


class PeakMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Peak Monitor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            flattened = {}
            for key, value in user_input.items():
                if isinstance(value, dict):
                    flattened.update(value)
                else:
                    flattened[key] = value

            user_input = flattened

            if CONF_ESTIMATION_SENSOR in user_input:
                est_sensor = user_input[CONF_ESTIMATION_SENSOR]
                if not est_sensor or str(est_sensor).strip() == "" or str(est_sensor).lower() == "none":
                    user_input[CONF_ESTIMATION_SENSOR] = None

            try:
                info = await validate_input(self.hass, user_input)

                if "error" in info:
                    errors["base"] = info["error"]
                else:
                    await _async_fire_config_choice_warnings(
                        self.hass, user_input, info.get("warnings", [])
                    )
                    return self.async_create_entry(title=info["title"], data=user_input)
            except Exception:
                errors["base"] = "unknown"

        # Pre-detect input unit from whatever sensor the user may have already
        # selected (handles the common case of a first-time setup where the form
        # is being shown for the first time and the entity ID is not yet known).
        # On re-show after a validation error we preserve the user's explicit choice.
        suggested_defaults: dict = {}
        if user_input is not None:
            # Re-show after error: carry forward what the user typed
            suggested_defaults = dict(user_input)
        else:
            # First show: try to auto-detect input unit — but we have no sensor yet.
            # The detection happens in validate_input; here we just show defaults.
            # The schema default for input_unit will be overridden after the sensor
            # is known (see validate_input auto-detect logic).
            pass

        return self.async_show_form(
            step_id="user",
            data_schema=_get_schema(suggested_defaults),
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return PeakMonitorOptionsFlow()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration of the integration."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            flattened = {}
            for key, value in user_input.items():
                if isinstance(value, dict):
                    flattened.update(value)
                else:
                    flattened[key] = value

            user_input = flattened

            for optional_sensor in [CONF_ESTIMATION_SENSOR, CONF_EXTERNAL_MUTE_SENSOR, CONF_EXTERNAL_REDUCED_SENSOR]:
                if optional_sensor not in user_input:
                    user_input[optional_sensor] = None
                elif user_input[optional_sensor]:
                    sensor_value = user_input[optional_sensor]
                    if str(sensor_value).strip() == "" or str(sensor_value).lower() == "none":
                        user_input[optional_sensor] = None

            updated_data = {**entry.data, **user_input}

            self.hass.config_entries.async_update_entry(
                entry,
                data=updated_data,
            )

            # Fire config-choice warnings (incompatible settings, sub-hour averaging).
            # These run here — not on startup — so they only appear after a deliberate
            # reconfigure, not on every HA restart.
            validation_result = await validate_input(self.hass, dict(updated_data))
            await _async_fire_config_choice_warnings(
                self.hass, updated_data, validation_result.get("warnings", []),
                entry_id=entry.entry_id,
            )

            await self.hass.config_entries.async_reload(entry.entry_id)

            return self.async_abort(reason="reconfigure_successful")

        current_config = dict(entry.data)
        # If the stored currency is a custom value (not in the dropdown options),
        # pre-populate the selector as "custom" and fill the custom_currency field.
        stored_currency = current_config.get("currency", "")
        if stored_currency and stored_currency not in CURRENCY_OPTIONS:
            current_config["currency"] = CURRENCY_CUSTOM
            current_config["custom_currency"] = stored_currency

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_get_options_schema(current_config),
        )


class PeakMonitorOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Peak Monitor."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            flattened = {}
            for key, value in user_input.items():
                if isinstance(value, dict):
                    flattened.update(value)
                else:
                    flattened[key] = value

            user_input = flattened

            # Handle custom currency
            currency = user_input.get(CONF_CURRENCY, DEFAULT_CURRENCY)
            custom_currency = user_input.pop("custom_currency", "")
            if currency == CURRENCY_CUSTOM and custom_currency:
                from .const import ISO_4217_CURRENCIES
                if custom_currency.upper() in ISO_4217_CURRENCIES:
                    user_input[CONF_CURRENCY] = custom_currency.upper()
                else:
                    user_input[CONF_CURRENCY] = DEFAULT_CURRENCY

            for optional_sensor in [CONF_ESTIMATION_SENSOR, CONF_EXTERNAL_MUTE_SENSOR, CONF_EXTERNAL_REDUCED_SENSOR]:
                if optional_sensor not in user_input:
                    user_input[optional_sensor] = None
                elif user_input[optional_sensor]:
                    sensor_value = user_input[optional_sensor]
                    if str(sensor_value).strip() == "" or str(sensor_value).lower() == "none":
                        user_input[optional_sensor] = None

            validation_result = await validate_input(self.hass, {**self.config_entry.data, **user_input})
            await _async_fire_config_choice_warnings(
                self.hass, {**self.config_entry.data, **user_input},
                validation_result.get("warnings", []),
                entry_id=self.config_entry.entry_id,
            )
            return self.async_create_entry(title="", data=user_input)

        current_config = {**self.config_entry.data, **self.config_entry.options}
        # If the stored currency is a custom value (not in the dropdown options),
        # pre-populate the selector as "custom" and fill the custom_currency field.
        stored_currency = current_config.get("currency", "")
        if stored_currency and stored_currency not in CURRENCY_OPTIONS:
            current_config = dict(current_config)
            current_config["currency"] = CURRENCY_CUSTOM
            current_config["custom_currency"] = stored_currency

        return self.async_show_form(
            step_id="init",
            data_schema=_get_options_schema(current_config),
        )
