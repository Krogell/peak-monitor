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
    CONF_HOLIDAYS,
    CONF_HOLIDAY_BEHAVIOR,
    CONF_WEEKEND_BEHAVIOR,
    CONF_WEEKEND_START_HOUR,
    CONF_WEEKEND_END_HOUR,
    CONF_RESET_VALUE,
    CONF_SENSOR_RESETS_EVERY_HOUR,
    CONF_INPUT_UNIT,
    CONF_OUTPUT_UNIT,
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
    DEFAULT_HOLIDAYS,
    DEFAULT_HOLIDAY_BEHAVIOR,
    DEFAULT_WEEKEND_BEHAVIOR,
    DEFAULT_WEEKEND_START_HOUR,
    DEFAULT_WEEKEND_END_HOUR,
    DEFAULT_RESET_VALUE,
    DEFAULT_SENSOR_RESETS_EVERY_HOUR,
    DEFAULT_INPUT_UNIT,
    DEFAULT_OUTPUT_UNIT,
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
    OUTPUT_UNIT_OPTIONS,
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input.

    Returns:
        Dictionary with 'title' on success, or 'error' key on failure.
    """
    consumption_state = hass.states.get(data[CONF_CONSUMPTION_SENSOR])
    if not consumption_state:
        return {"error": "consumption_sensor_not_found"}

    unit = consumption_state.attributes.get("unit_of_measurement", "Wh")
    if unit in ["kWh", "kilowatt_hour"]:
        data[CONF_INPUT_UNIT] = "kWh"
    else:
        data[CONF_INPUT_UNIT] = "Wh"

    estimation_sensor = data.get(CONF_ESTIMATION_SENSOR)
    if estimation_sensor is not None:
        est_str = str(estimation_sensor).strip()
        if est_str and est_str.lower() != "none":
            if not hass.states.get(estimation_sensor):
                return {"error": "estimation_sensor_not_found"}

    return {"title": data.get(CONF_NAME, "Peak Monitor")}


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
                        device_class="energy"
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

        # ========== Advanced ==========
        vol.Required("advanced_section"): section(
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
                    CONF_OUTPUT_UNIT,
                    default=defaults.get(CONF_OUTPUT_UNIT, DEFAULT_OUTPUT_UNIT)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=OUTPUT_UNIT_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="output_unit",
                    )
                ),
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
                        device_class="energy"
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

        # ========== Advanced ==========
        vol.Required("advanced_section"): section(
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
                    CONF_OUTPUT_UNIT,
                    default=defaults.get(CONF_OUTPUT_UNIT, DEFAULT_OUTPUT_UNIT)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=OUTPUT_UNIT_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="output_unit",
                    )
                ),
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
                    return self.async_create_entry(title=info["title"], data=user_input)
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=_get_schema(),
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

            await self.hass.config_entries.async_reload(entry.entry_id)

            return self.async_abort(reason="reconfigure_successful")

        current_config = entry.data

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_get_schema(current_config),
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

            for optional_sensor in [CONF_ESTIMATION_SENSOR, CONF_EXTERNAL_MUTE_SENSOR, CONF_EXTERNAL_REDUCED_SENSOR]:
                if optional_sensor not in user_input:
                    user_input[optional_sensor] = None
                elif user_input[optional_sensor]:
                    sensor_value = user_input[optional_sensor]
                    if str(sensor_value).strip() == "" or str(sensor_value).lower() == "none":
                        user_input[optional_sensor] = None

            return self.async_create_entry(title="", data=user_input)

        current_config = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=_get_options_schema(current_config),
        )
