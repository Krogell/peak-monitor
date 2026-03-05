"""Constants for the Peak Monitor integration."""

DOMAIN = "peak_monitor"

# Configuration keys
CONF_CONSUMPTION_SENSOR = "consumption_sensor"
CONF_ESTIMATION_SENSOR = "estimation_sensor"
CONF_EXTERNAL_MUTE_SENSOR = "external_mute_sensor"  # Binary sensor to mute tariff
CONF_EXTERNAL_REDUCED_SENSOR = "external_reduced_sensor"  # Binary sensor to activate reduced tariff
CONF_PRICE_PER_KW = "price_per_kw"
CONF_FIXED_MONTHLY_FEE = "fixed_monthly_fee"
CONF_ACTIVE_START_HOUR = "active_start_hour"
CONF_ACTIVE_END_HOUR = "active_end_hour"
CONF_ACTIVE_MONTHS = "active_months"
CONF_NUMBER_OF_PEAKS = "number_of_peaks"
CONF_HOLIDAYS = "holidays"  # Merged: official holidays + holiday evenings
CONF_HOLIDAY_BEHAVIOR = "holiday_behavior"
CONF_WEEKEND_BEHAVIOR = "weekend_behavior"
CONF_WEEKEND_START_HOUR = "weekend_start_hour"
CONF_WEEKEND_END_HOUR = "weekend_end_hour"
CONF_RESET_VALUE = "reset_value"
CONF_SENSOR_RESETS_EVERY_HOUR = "sensor_resets_every_hour"
CONF_INPUT_UNIT = "input_unit"
CONF_OUTPUT_UNIT = "output_unit"
CONF_ONLY_ONE_PEAK_PER_DAY = "only_one_peak_per_day"

# Reduced tariff configuration
CONF_DAILY_REDUCED_TARIFF_ENABLED = "daily_reduced_tariff_enabled"
CONF_REDUCED_START_HOUR = "reduced_start_hour"
CONF_REDUCED_END_HOUR = "reduced_end_hour"
CONF_REDUCED_FACTOR = "reduced_factor"
CONF_REDUCED_ALSO_ON_WEEKENDS = "reduced_also_on_weekends"

# Default values
DEFAULT_PRICE_PER_KW = 0
DEFAULT_FIXED_MONTHLY_FEE = 0
DEFAULT_ACTIVE_START_HOUR = 6
DEFAULT_ACTIVE_END_HOUR = 21
DEFAULT_ACTIVE_MONTHS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
DEFAULT_NUMBER_OF_PEAKS = 3
DEFAULT_RESET_VALUE = 500
DEFAULT_SENSOR_RESETS_EVERY_HOUR = False
DEFAULT_INPUT_UNIT = "Wh"
DEFAULT_OUTPUT_UNIT = "W"
DEFAULT_ONLY_ONE_PEAK_PER_DAY = True

# Default reduced tariff values
DEFAULT_DAILY_REDUCED_TARIFF_ENABLED = False
DEFAULT_REDUCED_START_HOUR = 21
DEFAULT_REDUCED_END_HOUR = 6
DEFAULT_REDUCED_FACTOR = 0.5
DEFAULT_REDUCED_ALSO_ON_WEEKENDS = False

# Behavior option keys (config values)
BEHAVIOR_NO_TARIFF = "no_tariff"
BEHAVIOR_REDUCED_TARIFF = "reduced_tariff"
BEHAVIOR_FULL_TARIFF = "full_tariff"

DEFAULT_HOLIDAY_BEHAVIOR = BEHAVIOR_NO_TARIFF
DEFAULT_WEEKEND_BEHAVIOR = BEHAVIOR_NO_TARIFF
DEFAULT_WEEKEND_START_HOUR = 6
DEFAULT_WEEKEND_END_HOUR = 21

# Sensor types
SENSOR_TARIFF = "tariff"
SENSOR_TARGET = "target"
SENSOR_RELATIVE = "relative"
SENSOR_DAILY_PEAK = "daily_peak"
SENSOR_PERCENTAGE = "percentage"
SENSOR_COST = "cost"
SENSOR_COST_INCREASE = "cost_increase"
SENSOR_INTERNAL_ESTIMATION = "internal_estimation"
SENSOR_INTERVAL_CONSUMPTION = "interval_consumption"
SENSOR_HOUR_CONSUMPTION = "hour_consumption"
SENSOR_ACTIVE = "active"  # Moved from binary_sensor

# Active state enum values (internal use)
ACTIVE_STATE_OFF = "off"
ACTIVE_STATE_REDUCED = "reduced"
ACTIVE_STATE_ON = "on"

# Tariff state keys (entity states - user-facing)
STATE_ACTIVE = "active"
STATE_INACTIVE = "inactive"
STATE_REDUCED = "reduced"

# Inactive reason keys (attribute values)
REASON_EXTERNAL_MUTE = "external_mute"
REASON_EXCLUDED_MONTH = "excluded_month"
REASON_HOLIDAY = "holiday"
REASON_WEEKEND = "weekend"
REASON_TIME_OF_DAY = "time_of_day"

# Reduced reason keys (attribute values)
REASON_EXTERNAL_CONTROL = "external_control"
# REASON_TIME_OF_DAY already defined above

# Holiday option keys (config values)
HOLIDAY_OFFICIAL = "official_holidays"
HOLIDAY_EPIPHANY_EVE = "epiphany_eve"
HOLIDAY_EASTER_EVE = "easter_eve"
HOLIDAY_MIDSUMMER_EVE = "midsummer_eve"
HOLIDAY_CHRISTMAS_EVE = "christmas_eve"
HOLIDAY_NEW_YEARS_EVE = "new_years_eve"

# Default holidays (merged: official holidays first, then holiday evenings)
DEFAULT_HOLIDAYS = [
    HOLIDAY_OFFICIAL,  # All red days
    HOLIDAY_EPIPHANY_EVE,
    HOLIDAY_EASTER_EVE,
    HOLIDAY_MIDSUMMER_EVE,
    HOLIDAY_CHRISTMAS_EVE,
    HOLIDAY_NEW_YEARS_EVE
]

# Unit option keys (config values)
UNIT_WH = "Wh"
UNIT_KWH = "kWh"
UNIT_W = "W"
UNIT_KW = "kW"

# Month option keys (config values - as strings for consistency with config)
MONTH_1 = "1"
MONTH_2 = "2"
MONTH_3 = "3"
MONTH_4 = "4"
MONTH_5 = "5"
MONTH_6 = "6"
MONTH_7 = "7"
MONTH_8 = "8"
MONTH_9 = "9"
MONTH_10 = "10"
MONTH_11 = "11"
MONTH_12 = "12"

# Month options (keys only, labels from translations)
MONTH_OPTIONS = [MONTH_1, MONTH_2, MONTH_3, MONTH_4, MONTH_5, MONTH_6, 
                 MONTH_7, MONTH_8, MONTH_9, MONTH_10, MONTH_11, MONTH_12]

# Weekend behavior options (keys only, labels from translations)
WEEKEND_BEHAVIOR_OPTIONS = [BEHAVIOR_NO_TARIFF, BEHAVIOR_REDUCED_TARIFF, BEHAVIOR_FULL_TARIFF]

# Holiday behavior options (keys only, labels from translations)
HOLIDAY_BEHAVIOR_OPTIONS = [BEHAVIOR_NO_TARIFF, BEHAVIOR_REDUCED_TARIFF]

# Input unit options (keys only, labels from translations)
INPUT_UNIT_OPTIONS = [UNIT_WH, UNIT_KWH]

# Output unit options (keys only, labels from translations)
OUTPUT_UNIT_OPTIONS = [UNIT_W, UNIT_KW]

# Holiday options (keys only, labels from translations)
HOLIDAY_OPTIONS = [
    HOLIDAY_OFFICIAL,
    HOLIDAY_EPIPHANY_EVE,
    HOLIDAY_EASTER_EVE,
    HOLIDAY_MIDSUMMER_EVE,
    HOLIDAY_CHRISTMAS_EVE,
    HOLIDAY_NEW_YEARS_EVE
]

# Official Swedish public holidays (red days) - used when "official_holidays" is selected
OFFICIAL_HOLIDAYS = [
    "new_years_day", "epiphany", "good_friday", "easter_sunday", "easter_monday",
    "may_day", "ascension_day", "national_day", "whit_sunday",
    "midsummer_day", "all_saints_day", "christmas_day", "boxing_day"
]

# Keep old holiday names for reference (not shown in UI)
