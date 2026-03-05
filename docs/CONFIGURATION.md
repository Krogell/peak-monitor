# Configuration Guide

This guide explains every configuration option available in the Peak Monitor integration.

The options are presented in the same order as they appear in the configuration flow.

## Table of Contents
- [Basic Setup](#basic-setup)
- [Weekdays](#weekdays)
- [Weekends & Holidays](#weekends--holidays)
- [Periodic Reduced Tariff](#periodic-reduced-tariff)
- [Advanced](#advanced)

➡️ **Looking for ready-made settings for your DSO?** See [Configuration Examples](CONFIGURATION_EXAMPLES.md).

---

## Basic Setup

### Consumption Sensor
**Field:** `consumption_sensor`  
**Type:** Entity selector (Energy sensor)  
**Required:** Yes  
**Description:** The sensor that measures your hourly power consumption. This is the primary input for the integration.

**Important Notes:**
- The sensor must have device class "energy"
- The unit will be automatically detected (Wh or kWh)
- Make sure this sensor updates regularly (at least once per hour)

**Example sensors:**
- `sensor.power_consumption` – from your energy metre
- `sensor.hourly_energy` – from your solar inverter
- `sensor.grid_consumption` – from your utility metre

### Sensor Resets Every Hour
**Field:** `sensor_resets_every_hour`  
**Type:** Boolean (checkbox)  
**Default:** No (unchecked)  
**Description:** Indicates whether your consumption sensor resets to 0 at the start of each hour, or whether it is cumulative.

**When to check this:**
- Your sensor shows interval consumption (e.g., "523 Wh" for the hour)
- The value resets to 0 or near 0 at the beginning of each hour

**When to uncheck this:**
- Your sensor is cumulative/monotonic (always increasing)
- The integration will calculate interval consumption from the difference

### Number of Peaks to Track
**Field:** `number_of_peaks`  
**Type:** Dropdown (1–10)  
**Default:** 3  
**Description:** How many monthly peak consumption hours are tracked for tariff calculation. Swedish electricity network fees are typically based on the average of the top 3 peaks.

### Only Count One Peak per Day
**Field:** `only_one_peak_per_day`  
**Type:** Boolean (checkbox)  
**Default:** Yes (checked)  
**Description:** When enabled, only the single highest hourly reading per day can be recorded as a peak. This prevents one unusual day from counting multiple times in the average.

### Price per kW
**Field:** `price_per_kwh/h`  
**Type:** Number  
**Default:** 0  
**Description:** The price per kWh/h used for cost calculations (in SEK). Set to your actual network fee rate for accurate cost estimates.

### Fixed Monthly Fee
**Field:** `fixed_monthly_fee`  
**Type:** Number  
**Default:** 0  
**Description:** A fixed monthly network fee (in SEK) added on top of the peak-based cost. This represents the standing charge component of your network fee.

### Active Months
**Field:** `active_months`  
**Type:** Multi-select dropdown  
**Default:** All activated
**Description:** The calendar months during which the tariff is active. Outside these months the tariff is always inactive. Some of the Swedish peak tariff apply only during winter months.

---

## Weekdays

### Start Hour
**Field:** `active_start_hour`  
**Type:** Dropdown (0–23)  
**Default:** 6  
**Description:** The hour at which tariff monitoring begins on weekdays. The tariff is inactive before this hour.

### End Hour
**Field:** `active_end_hour`  
**Type:** Dropdown (0–23)  
**Default:** 21  
**Description:** The hour at which tariff monitoring ends on weekdays. When this is the same as Start Hour, the tariff is monitored for the full 24 hours.

---

## Weekends & Holidays

### Weekend Behaviour
**Field:** `weekend_behavior`  
**Type:** Dropdown  
**Default:** No tariff  
**Options:**
- **No tariff** – tariff is completely inactive on weekends
- **Reduced tariff** – peaks counted at a reduced weight
- **Full tariff** – weekday hour logic applies on weekends

**Description:** Controls how the tariff behaves on Saturdays and Sundays, within the weekend time interval defined below.

### Weekend Start Hour
**Field:** `weekend_start_hour`  
**Type:** Dropdown (0–23)  
**Default:** 6  
**Description:** The hour at which the weekend behaviour begins on Saturdays and Sundays. Before this hour, the tariff is inactive regardless of the Weekend Behaviour setting. If this is equal to Weekend End Hour, the behaviour applies for the full day.

### Weekend End Hour
**Field:** `weekend_end_hour`  
**Type:** Dropdown (0–23)  
**Default:** 21  
**Description:** The hour at which the weekend behaviour ends on Saturdays and Sundays. At and after this hour, the tariff is inactive regardless of the Weekend Behaviour setting. If this is equal to Weekend Start Hour, the behaviour applies for the full day.

**Examples:**

| Weekend Start | Weekend End | Effect |
|---|---|---|
| 6 | 21 | Weekend behaviour active 06:00–20:59, tariff off outside this window |
| 0 | 0 | Weekend behaviour active all day (equal hours = full day) |
| 8 | 18 | Weekend behaviour active 08:00–17:59 only |

### Holiday Behaviour
**Field:** `holiday_behavior`  
**Type:** Dropdown  
**Default:** No tariff  
**Options:**
- **No tariff** – tariff is completely inactive on holidays
- **Reduced tariff** – peaks counted at a reduced weight

**Description:** Controls how the tariff behaves on holidays and holiday evenings defined in "Define Holidays".

### Define Holidays
**Field:** `holidays`  
**Type:** Multi-select dropdown  
**Default:** All options selected  
**Options:**
- **Official holidays (red days)** – all Swedish public holidays
- **Epiphany Eve** (5 January)
- **Easter Eve**
- **Midsummer Eve**
- **Christmas Eve** (24 December)
- **New Year's Eve** (31 December)

**Description:** Select which days and holiday evenings should trigger the Holiday Behaviour. Only the selected items are affected.

---

## Periodic Reduced Tariff

### Enable Daily Reduced Tariff
**Field:** `daily_reduced_tariff_enabled`  
**Type:** Boolean (checkbox)  
**Default:** No (unchecked)  
**Description:** When enabled, a daily time window is active during which consumption is counted with a reduced weight. Useful for overnight hours when the tariff impact should be lower.

### Reduced Period Start Hour
**Field:** `reduced_start_hour`  
**Type:** Dropdown (0–23)  
**Default:** 21  
**Description:** The hour at which the reduced tariff period begins each day.

### Reduced Period End Hour
**Field:** `reduced_end_hour`  
**Type:** Dropdown (0–23)  
**Default:** 6  
**Description:** The hour at which the reduced tariff period ends each day. A period that crosses midnight (e.g., 21 to 6) is correctly handled.

### Also on Weekends
**Field:** `reduced_also_on_weekends`  
**Type:** Boolean (checkbox)  
**Default:** No (unchecked)  
**Description:** When checked, the daily reduced tariff window also applies on Saturdays and Sundays. Outside the reduced window, the normal Weekend Behaviour setting still governs the weekend state.

**Use case — Ellevio (and similar DSOs):** Ellevio weights night-time consumption at 50% every night of the week, including weekends. To replicate this:
- Enable Daily Reduced Tariff, set window to 22–06, factor 0.5
- Check **Also on Weekends**
- Set Weekend Behaviour to **No tariff** (so Saturday/Sunday daytime hours are inactive)

This produces: reduced (22–06 every day) · inactive (weekday daytime outside active hours) · active (weekday daytime inside active hours) · inactive (weekend daytime).

---

## Advanced

### Estimation Sensor (optional)
**Field:** `estimation_sensor`  
**Type:** Entity selector (Energy sensor, optional)  
**Default:** None  
**Description:** An optional external sensor that provides an estimate of the current hour's consumption. If left empty, the integration uses its own built-in estimation based on consumption so far in the current hour. Please note, that once configured, it can only be exchanged, not removed.

### External Reduce Sensor (optional)
**Field:** `external_reduced_sensor`  
**Type:** Entity selector (Binary sensor, optional)  
**Default:** None  
**Description:** An optional binary sensor. When this sensor is **ON**, the tariff automatically enters reduced mode, regardless of the time-of-day schedule. Useful for integrations with dynamic tariff controls or smart home automations. Please note, that once configured, it can only be exchanged, not removed.

### External Mute Sensor (optional)
**Field:** `external_mute_sensor`  
**Type:** Entity selector (Binary sensor, optional)  
**Default:** None  
**Description:** An optional binary sensor. When this sensor is **ON**, the tariff is completely muted (inactive). This takes priority over all other settings. Useful for manual overrides or for non-Swedish users who want external control. Please note, that once configured, it can only be exchanged, not removed.

### Reduced Tariff Multiplication Factor
**Field:** `reduced_factor`  
**Type:** Number (float)  
**Default:** 0.5  
**Range:** 0.01 – 1.0  
**Description:** The factor applied to consumption during reduced tariff periods. A value of `0.5` means that consumption during reduced hours counts as 50% of actual consumption when calculating peak usage. This affects both the internal tracking and the target consumption calculation. Adjust this if your utility applies a different reduction ratio.

### Reset Value
**Field:** `reset_value`  
**Type:** Number  
**Default:** 500  
**Description:** The value (in Wh) that the internal tracking resets to at the beginning of each month. This represents a baseline/safety buffer below which the tracked peak will not drop.

### Output Value
**Field:** `output_unit`  
**Type:** Dropdown  
**Default:** W  
**Options:**
- **W** – Watt
- **kW** – Kilowatt

**Description:** The unit used for output sensor values displayed in Home Assistant. Adjust to your liking.

---

➡️ **See [Configuration Examples](CONFIGURATION_EXAMPLES.md)** for ready-made settings for Ellevio, Göteborg Energi, Vattenfall, and other common Swedish DSOs.
