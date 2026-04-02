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
- The unit is automatically detected from the sensor's `unit_of_measurement` attribute
- Both energy sensors (Wh/kWh) and power sensors (W/kW) are supported — see *Input Unit* under Advanced for details
- Make sure the sensor updates regularly (at the end of each interval is the bare minimum)

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
**Description:** How many monthly peak consumption hours are tracked for tariff calculation. Swedish electricity network fees are commonly based on the average of the top 3 peaks.

### Only Count One Peak per Day
**Field:** `only_one_peak_per_day`  
**Type:** Boolean (checkbox)  
**Default:** Yes (checked)  
**Description:** When enabled, only the single highest hourly reading per day can be recorded as a peak. This prevents one unusual day from counting multiple times in the average.

### Daily Peak Averaging (peaks per day)
**Field:** `daily_peaks_averaged`  
**Type:** Dropdown (1–5)  
**Default:** 1 (disabled)  
**Description:** Sets how many of the highest intra-day readings are averaged together to produce the daily committed value.

- **1** — Standard behaviour. The single highest hourly reading of the day is recorded as the daily peak.
- **2** — The two highest hourly readings of the day are averaged. This is the model used by, for example, **Jönköping Energi**.
- **3–5** — The N highest hourly readings are averaged.

When this is set to more than 1, individual **Daily Sub-Peak** sensors are created (one per slot, disabled by default) that show each of the intra-day readings used in the average. The **Daily Peak** sensor shows the resulting average value, along with the sub-peak values as attributes.

> **Requirement:** This setting requires *Only count one peak per day* to be enabled. If you disable that option while this is set above 1, the configuration will automatically be overridden.

> **Target behaviour:** When daily averaging is active and today's average already qualifies for the monthly peak list, the target threshold shown is the **lowest of the current daily sub-peaks** — the weakest slot that could still be improved today.

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

### Measurement Interval
**Field:** `interval_minutes`  
**Type:** Dropdown  
**Default:** 60 min (standard hourly)  
**Options:** 6, 12, 15, 20, 30, 60, 120 minutes  
**Description:** The length of each measurement interval. At the end of each interval the accumulated consumption is committed as a candidate peak, replacing the current lowest peak if it qualifies.

The default of 60 minutes matches the Swedish grid standard (one peak per clock hour). Shorter intervals allow finer granularity — useful if your utility or contract measures peaks on shorter periods. Longer intervals (120 min) can be used if your contract averages over two-hour blocks.

**How it works:**
- Boundaries are aligned to the top of the hour (minute :00). For example, a 15-minute interval fires at :00, :15, :30, and :45 of each hour.
- The target sensor remains stable within each interval period, just as it does hour-to-hour in the standard 60-minute mode.
- The interval consumed sensor shows accumulated consumption within the current interval.
- 120 minutes fires at :00 of every other hour (00:00, 02:00, 04:00 …).

**Note:** Changing this setting on an existing integration takes effect immediately after saving — no restart required.

### Reset Value
**Field:** `reset_value`  
**Type:** Number  
**Default:** 500  
**Description:** The value (in Wh) that the internal tracking resets to at the beginning of each period. This represents a baseline/safety buffer below which the tracked peak will not drop. Ideally this value shall be configured to slightly lower than the expected lowest period peak.
If configured to very small value, it will lead to a lot of unnecessary warnings and possibly triggering automations early in the monitoring period, where the actual outcome will be way larger either way.
A very large value, bigger than your smallest counted peak, will instead give you a false picture of monthly costs (larger than actual). Knowing this, it can be set to a value that is deemed as acceptable outcome.

**Example:** Actual counted peaks of the period are measured to 6000, 7500 and 9000 W. If Reset Value is 1000 W, many warnings are triggered along the way. If Reset Value is set to 8000 W, only the peak of 9 kW may trigger warnings and automations (of course, warning and automations are depending on use case).

### Reset Interval
**Field:** `reset_interval`  
**Type:** Dropdown  
**Default:** Monthly  
**Options:**
- **Weekly** – Period peaks reset every Monday at midnight
- **Monthly** – Period peaks reset at the start of each calendar month (default)
- **Manual only** – Peaks are never reset automatically; use the `peak_monitor.reset_peak` service to reset manually

**Description:** Controls how often the period monthly peaks are automatically cleared. In **Manual only** mode, the daily peak (current-hour tracker) still resets each night at midnight, but the stored period peaks accumulate indefinitely until manually reset.

### Input Unit
**Field:** `input_unit`  
**Type:** Dropdown  
**Default:** Wh  
**Options:**
- **Wh** – Watt-hour (energy sensor, resets each hour)
- **kWh** – Kilowatt-hour (energy sensor, cumulative)
- **W** – Watt (power sensor; integration is calculated automatically)
- **kW** – Kilowatt (power sensor; integration is calculated automatically)

**Description:** The unit of measurement reported by your consumption sensor. For power sensors (W/kW), the integration is calculated using trapezoidal integration between sensor readings. If Home Assistant restarts, the partial integration for that time period is lost.

> **⚠️ Recommendation:** Prefer an energy sensor (Wh/kWh) over a power sensor (W/kW). Energy sensors may continue to log consumption even when Home Assistant is offline, depending on your hardware. Power sensors rely on real-time polling and any gap (HA restart, sensor unavailability) results in missing data for that interval.

### Output Unit
**Field:** `output_unit`  
**Type:** Dropdown  
**Default:** W  
**Options:**
- **W** – Watt
- **kW** – Kilowatt

**Description:** The unit used for output sensor values displayed in Home Assistant. Adjust to your liking.

### Currency
**Field:** `currency`  
**Type:** Dropdown  
**Default:** SEK  
**Options:**
- **SEK** – Swedish Krona
- **EUR** – Euro
- **USD** – US Dollar
- **Custom** – Enter any ISO 4217 currency code (e.g. NOK, DKK, GBP)

**Description:** The currency used for cost sensor values. Affects both the Period Cost sensor and the Cost Increase Forecast sensor. The selected (or custom) currency code is used as the unit of measurement for cost sensors.

---

## Reset Peak Service

The `peak_monitor.reset_peak` service allows you to manually reset one or all period peaks for a specific instance. This is useful for automations or when you want to start fresh mid-period.

### Service Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `config_entry_id` | No | String | Config entry ID of the instance to target. **Omit only if you have a single instance** — otherwise all instances are reset. |
| `peak_index` | No | Integer (1–10) | 1-based index of the monthly peak slot to reset. Omit to reset all peaks for the targeted instance. |
| `reset_value` | No | Number | Value to reset to (in W/kW). Defaults to the configured reset value. Cannot exceed the current peak value — it is automatically clamped. |

### Finding your Config Entry ID

In Home Assistant Developer Tools, open the Template editor and evaluate:

```jinja
{{ integration_entries('peak_monitor') }}
```

This returns a list of entry IDs for all Peak Monitor instances. Alternatively, navigate to **Settings → Devices & Services → Peak Monitor**, click an instance, and copy the ID from the URL bar (`/config/integrations/integration/peak_monitor/<entry_id>`).

### Example Automation

```yaml
automation:
  - alias: "Reset Peak 1 at start of month"
    trigger:
      - platform: time
        at: "00:01:00"
    condition:
      - condition: template
        value_template: "{{ now().day == 1 }}"
    action:
      - service: peak_monitor.reset_peak
        data:
          config_entry_id: "abc123def456abc123def456abc123de"
          peak_index: 1
```

> **Note:** The reset value cannot be set higher than the current peak value. If a higher value is specified, it is automatically clamped to the current value. Period average and price indicators are recalculated immediately after the service call.

---

➡️ **See [Configuration Examples](CONFIGURATION_EXAMPLES.md)** for ready-made settings for Ellevio, Göteborg Energi, Vattenfall, and other common Swedish DSOs.
