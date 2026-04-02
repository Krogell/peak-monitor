# Installation Guide — Peak Monitor

This guide covers installation and configuration of the Peak Monitor integration for Home Assistant.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Sensors](#sensors)
5. [Automations](#automations)
6. [Troubleshooting](#troubleshooting)
7. [Updating](#updating)

---

## Prerequisites

- Home Assistant 2024.6.0 or later
- A sensor that tracks your power or energy consumption. Either:
  - **Hourly-resetting sensor** — resets to 0 at the start of each hour
  - **Cumulative sensor** — continuously increasing value (e.g. total kWh)
- *(Optional)* An external sensor that forecasts the current interval's consumption

---

## Installation

### Method 1: HACS (Recommended)

**Step 1 — Install HACS** (skip if already installed)
Follow the official guide at https://hacs.xyz/docs/use, then restart Home Assistant.

**Step 2 — Add the repository**
1. Go to **HACS → Integrations**
2. Click the **three-dot menu** (⋮) → **Custom repositories**
3. Add `https://github.com/krogell/peak-monitor` with category **Integration**
4. Click **Add**

**Step 3 — Install Peak Monitor**
1. Search for **Peak Monitor** in HACS → Integrations
2. Click it, then click **Download**
3. Select the latest version and confirm

**Step 4 — Restart Home Assistant**
Go to **Settings → System → Restart**.

---

### Method 2: Manual Installation

**Step 1 — Download**
Download the latest release ZIP from the GitHub repository and extract it.

**Step 2 — Copy files**
Copy the `peak_monitor` folder into your Home Assistant configuration directory:

```
/config/custom_components/peak_monitor/
```

The directory should contain:

```
/config/
└── custom_components/
    └── peak_monitor/
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── holidays.py
        ├── manifest.json
        ├── sensor.py
        ├── state_mapper.py
        ├── strings.json
        ├── utils.py
        └── translations/
            ├── en.json
            └── sv.json
```

**Step 3 — Restart Home Assistant**
Go to **Settings → System → Restart**.

---

## Configuration

### Step 1: Add the integration

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration** (bottom right)
3. Search for **Peak Monitor** and select it

The configuration form is divided into collapsible sections. All sections are presented in a single form — there is no multi-step wizard.

---

### Section: Basic Setup

| Field | Default | Description |
|---|---|---|
| **Name** | `Peak Monitor` | Friendly name for this instance. Used as the prefix for all entity IDs. You can run multiple instances with different names. |
| **Consumption Sensor** | *(required)* | The entity that measures your power or energy consumption. Example: `sensor.electricity_meter`. |
| **Sensor Resets Every Hour** | Off | Enable if your consumption sensor resets to 0 at the start of each hour. Leave off for cumulative (always-increasing) sensors. |
| **Number of Peaks** | `3` | How many monthly peak hours to track. Swedish tariffs commonly average the top 3 hours. Range: 1–10. |
| **Only One Peak per Day** | On | When enabled, only the single highest hour each day can enter the monthly peak list. Disable to allow multiple peaks per day. |
| **Daily Peaks Averaged** | `1` | In multiple-peaks-per-day mode, how many intra-day sub-peaks are averaged together before committing as the day's contribution. Only relevant when *Only One Peak per Day* is off. |
| **Price per kW** | `0` | The capacity price you pay per kW. Set to your DSO's actual rate to enable cost sensors. Leave at 0 to disable cost tracking. |
| **Fixed Monthly Fee** | `0` | A fixed monthly standing charge added on top of the variable tariff cost. |
| **Active Months** | All 12 months | The calendar months during which tariff tracking is active. Outside these months the tariff is always inactive. |

---

### Section: Weekdays

| Field | Default | Description |
|---|---|---|
| **Active Start Hour** | `6` | Hour when tariff monitoring begins on weekdays (0–23). |
| **Active End Hour** | `21` | Hour when tariff monitoring ends on weekdays (0–23). Setting this equal to Start Hour enables 24-hour monitoring. |

---

### Section: Weekends

| Field | Default | Description |
|---|---|---|
| **Weekend Behaviour** | `No tariff` | How the tariff behaves on Saturdays and Sundays within the weekend time window. Options: **No tariff**, **Reduced tariff**, **Full tariff**. |
| **Weekend Start Hour** | `6` | Hour when weekend behaviour begins. Before this hour the tariff is inactive regardless of the Weekend Behaviour setting. Setting this equal to Weekend End Hour makes the behaviour apply all day. |
| **Weekend End Hour** | `21` | Hour when weekend behaviour ends. At and after this hour the tariff is inactive. |

---

### Section: Holidays

| Field | Default | Description |
|---|---|---|
| **Holiday Behaviour** | `No tariff` | How the tariff behaves on defined holidays. Options: **No tariff**, **Reduced tariff**. |
| **Define Holidays** | Official holidays | The Swedish public holidays (and optionally their eves) to exclude or reduce. Select individual holiday eves (e.g. Julafton, Nyårsafton) to match your DSO's specific rules. |

---

### Section: Periodic Reduced Tariff

| Field | Default | Description |
|---|---|---|
| **Daily Reduced Tariff Enabled** | Off | Enable a daily time window where consumption is weighted at a reduced rate. Useful for overnight hours with lower tariff impact. |
| **Also on Weekends** | Off | When enabled, the reduced window also fires on Saturdays and Sundays. Weekend behaviour outside the reduced window is still governed by the Weekend Behaviour setting. |
| **Reduced Start Hour** | `21` | Hour when the reduced window begins each day. |
| **Reduced End Hour** | `6` | Hour when the reduced window ends. A window crossing midnight (e.g. 21–06) is handled correctly. |

---

### Section: External Sensors

| Field | Default | Description |
|---|---|---|
| **Estimation Sensor** | *(empty)* | Optional entity providing an external forecast of the current interval's consumption. When set, the built-in Interval Consumption Forecast sensor is not created. |
| **External Reduced Sensor** | *(empty)* | Optional binary sensor. When **ON**, the tariff enters reduced mode regardless of the time schedule. Note: once configured this field can only be changed to a different sensor, not cleared. |
| **External Mute Sensor** | *(empty)* | Optional binary sensor. When **ON**, the tariff is completely muted (inactive), overriding all other settings. Note: once configured this field can only be changed to a different sensor, not cleared. |

---

### Section: Advanced

| Field | Default | Options | Description |
|---|---|---|---|
| **Input Unit** | `auto` | `auto`, `Wh`, `kWh`, `W`, `kW` | Unit of your consumption sensor. `auto` reads the unit from the sensor's `unit_of_measurement` attribute. Override if auto-detection gives incorrect results. |
| **Reduced Factor** | `0.5` | 0.01–1.0 | Weight applied to consumption during reduced-tariff periods. `0.5` means consumption counts as 50% of the actual value. |
| **Reset Value** | `500` | ≥ 0 | Initial peak placeholder (Wh) at the start of a new period. Prevents zero-based distortion in the monthly average before any real peaks are recorded. |
| **Measurement Interval** | `60` | 6, 12, 15, 20, 30, 60, 120 | Duration of each tracking interval in minutes. Match this to your grid operator's billing interval. |
| **Reset Interval** | `Monthly` | Weekly, Monthly, Manual only | How often period peaks are automatically cleared. **Weekly** resets every Monday at midnight; **Monthly** resets on the 1st; **Manual only** never resets automatically. |
| **Output Unit** | `W` | `W`, `kW` | Unit used for power sensors. |
| **Currency** | `SEK` | SEK, EUR, USD, Custom | Currency for cost sensors. Choose **Custom** to enter any 3-letter ISO currency code. |

---

## Sensors

After saving, Peak Monitor creates the following entities. Entity IDs use the instance name as prefix — examples below assume the default name `peak_monitor`.

### Always created

| Sensor | Entity ID | Description |
|---|---|---|
| **Period Average** | `sensor.peak_monitor_period_average` | Average of your top N monthly peaks — your current tariff level. This is the number that determines your monthly capacity fee. |
| **Period Cost** | `sensor.peak_monitor_period_cost` | Estimated total monthly capacity fee. Only meaningful when Price per kW is configured. |
| **Cost Increase Forecast** | `sensor.peak_monitor_cost_increase_forecast` | Real-time estimate of how much the monthly cost would increase if the current interval is committed as a new peak. |
| **Target** | `sensor.peak_monitor_target` | Recommended consumption ceiling for the current interval. Stay below this to avoid increasing your tariff. |
| **Target Headroom** | `sensor.peak_monitor_target_headroom` | Remaining room below target. Positive = under target, negative = over target. |
| **Immediate Headroom** | `sensor.peak_monitor_immediate_headroom` | Headroom based only on committed consumption so far, without blending in live pace. |
| **Safe Headroom** | `sensor.peak_monitor_safe_headroom` | Conservative headroom estimate used in averaging mode. |
| **Target Usage Percentage** | `sensor.peak_monitor_target_usage_percentage` | Estimated interval consumption as a percentage of target. Useful for automation triggers. |
| **Status** | `sensor.peak_monitor_status` | Current tariff state: `active`, `reduced`, or `inactive`. |
| **Daily Peak** | `sensor.peak_monitor_daily_peak` | Highest interval consumption recorded today. Resets at midnight. In averaging mode this is the average of the top N intra-day sub-peaks committed so far. |
| **Period Peak 1–N** | `sensor.peak_monitor_period_peak_1` … `_period_peak_N` | Individual monthly peak values, ranked highest to lowest. Hidden by default — enable in entity settings to track them separately. The same values are available as attributes on Period Average. |

### Created conditionally

| Sensor | Entity ID | Condition |
|---|---|---|
| **Interval Consumption Forecast** | `sensor.peak_monitor_interval_consumption_forecast` | Only created when no external estimation sensor is configured. Shows the integration's built-in forecast for the current interval. |
| **Interval Consumption** | `sensor.peak_monitor_interval_consumption` | Only created when the consumption sensor is cumulative (does not reset hourly). Shows accumulated consumption for the current interval. |
| **Consumption Pace Deviation** | `sensor.peak_monitor_consumption_pace_deviation` | Deviation of actual consumption pace from ideal linear pace through the interval. |
| **Daily Sub-Peak 1–N** | `sensor.peak_monitor_daily_sub_peak_1` … | Only created in multiple-peaks-per-day mode (*Only One Peak per Day* off). One sensor per configured sub-peak. |

### Attributes on Period Average

The `sensor.peak_monitor_period_average` entity exposes these state attributes:

| Attribute | Description |
|---|---|
| `period_peak_1`, `period_peak_2`, … | Individual monthly peak values, highest first |
| `period_peak_1_is_today`, … | `true` when that slot belongs to today's daily peak |
| `includes_today` | Whether today's daily peak is currently influencing the average |
| `last_updated` | Timestamp of the last committed peak, rounded to the nearest minute |
| `price` | Current monthly tariff cost in your currency *(only if Price per kW is configured)* |

---

## Automations

### Notify when approaching target

```yaml
automation:
  - alias: "Peak Monitor Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.peak_monitor_target_usage_percentage
        above: 95
    action:
      - service: notify.mobile_app
        data:
          message: >
            Warning: At {{ states('sensor.peak_monitor_target_usage_percentage') | round }}%
            of power target. Headroom: {{ states('sensor.peak_monitor_target_headroom') }} W
```

### Stop EV charging when over target

```yaml
automation:
  - alias: "Pause EV charger when over peak target"
    trigger:
      - platform: numeric_state
        entity_id: sensor.peak_monitor_target_headroom
        below: 0
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.ev_charger
```

### Change indicator light based on tariff state

```yaml
automation:
  - alias: "Tariff state indicator"
    trigger:
      - platform: state
        entity_id: sensor.peak_monitor_status
    action:
      - service: light.turn_on
        target:
          entity_id: light.status_indicator
        data:
          color_name: >
            {% if trigger.to_state.state == 'active' %}
              yellow
            {% elif trigger.to_state.state == 'reduced' %}
              orange
            {% else %}
              white
            {% endif %}
```

---

## Troubleshooting

### Integration not found after installation

1. Confirm the files are at `/config/custom_components/peak_monitor/`
2. Verify `manifest.json` exists in the folder
3. Restart Home Assistant again
4. Clear your browser cache (Ctrl+F5 / Cmd+Shift+R)
5. Check logs at **Settings → System → Logs**

### Sensors show Unavailable or Unknown

- **Consumption sensor not working** — verify the sensor is available in **Developer Tools → States** and returning numeric values.
- **Tariff is inactive** — sensors like Target and Target Usage Percentage only show values when the tariff is active. Check the **Status** sensor to confirm.
- **Wrong configuration** — reconfigure at **Settings → Devices & Services → Peak Monitor → Configure**.

### Interval Consumption Forecast not created

This sensor is only created when no external estimation sensor is set. If you have one configured, remove it in the options and restart. The internal sensor will then be created.

### Period peaks not resetting

Peaks reset automatically per the **Reset Interval** setting (default: 1st of each month at midnight).

- Verify Home Assistant was running at midnight on the reset date.
- Check logs for errors during the reset.

**Manual reset:** Use the `peak_monitor.reset_peak` service. To reset all peaks, call it without a `peak_index`. See **Settings → Developer Tools → Services**.

### Cost sensors show zero

Verify that **Price per kW** is set to a non-zero value. The default is `0`, which disables cost calculation.

### Incorrect consumption values

- Check that **Input Unit** matches your sensor. Use `auto` for automatic detection, or override with `Wh`, `kWh`, `W`, or `kW`.
- Check that **Sensor Resets Every Hour** matches your sensor's actual behaviour.
- In cumulative mode, check that the **Interval Consumption** sensor delta looks correct between interval boundaries.

### Enable debug logging

Add to `configuration.yaml` and restart:

```yaml
logger:
  default: info
  logs:
    custom_components.peak_monitor: debug
```

Logs are at **Settings → System → Logs**. Filter for `custom_components.peak_monitor`.

---

## Updating

### Via HACS

1. Go to **HACS → Integrations**
2. Find **Peak Monitor** — click **Update** if available
3. Restart Home Assistant

### Manual update

1. Download the new release and replace all files in `/config/custom_components/peak_monitor/`
2. Restart Home Assistant
3. Review the release notes for any breaking changes or required reconfiguration

---

## Getting Help

1. Check **Settings → System → Logs** for entries starting with `custom_components.peak_monitor`
2. Open an issue at https://github.com/krogell/peak-monitor/issues

   Include: Home Assistant version, Peak Monitor version, relevant log entries, your configuration (remove sensitive data), and steps to reproduce.
