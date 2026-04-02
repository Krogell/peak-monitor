# Peak Monitor 2026.4 — Release Notes

This release adds significant new functionality from 2026.3, along with several sensor renames that require attention when upgrading.

---

## New features

### Daily peak averaging mode

Some grid operators calculate the monthly capacity fee based on the average of the N highest hourly readings within each day, rather than a single daily peak. The most common model (used by e.g. Jönköping Energi) averages the two highest hours.

A new *Daily Peak Averaging* option in the configuration sets how many intra-day peaks are averaged. When set above 1, the integration creates individual **Daily Sub-Peak** sensors for each slot, and the **Daily Peak Average** sensor shows the resulting average that will be committed at midnight.

### Immediate Headroom and Safe Headroom sensors (averaging mode)

Two new sensors are created when daily peak averaging is active:

**Immediate Headroom** — the absolute maximum you can consume this interval without adding any cost to your monthly bill. This is a hard ceiling for one-off high-draw events. The documentation explains why you should aim for the Target sensor in normal use, and only treat Headroom as the emergency ceiling.

**Safe Headroom** — the consumption level that is guaranteed not to worsen any sub-peak slot for the rest of the day. Useful for automations (EV chargers, heat pumps) that need a threshold they can always stay under without risk.

### Configurable measurement interval

The tariff tracking interval is now configurable from 6 to 120 minutes. This supports grid operators that use 15-minute or 30-minute intervals instead of the standard 60 minutes.

### Power sensor input (W/kW)

In addition to energy sensors (Wh/kWh), the integration now accepts instantaneous power sensors as input. Power readings are integrated over time using trapezoidal integration. Note that energy sensors remain recommended — see the sensor reference for details.

### Configurable currency

The currency used for cost sensors is now configurable rather than hardcoded to SEK. Any ISO 4217 currency code is accepted.

### Configurable reset interval

The monthly peaks list can now reset on a weekly cycle in addition to the default monthly reset. Manual reset via service call is also supported.

### Real-time cost impact sensor

The **Cost Increase Forecast** sensor shows in real currency how much your monthly bill would increase if the current interval ends as a new peak. This updates live during each interval.

---

## ⚠️ Sensor renames — action required

Several sensors have been renamed for clarity and consistency with coming features. Because entity IDs change, **Home Assistant may create new entities and mark the old ones as unavailable**. You may also have / want to use "Recreate entity IDs" feature in HA. Update any dashboards, automations, or scripts that reference the old entity IDs after upgrading.

| Old name | New name | Old entity ID suffix | New entity ID suffix |
|---|---|---|---|
| Power Grid Peak Tariff | **Period Cost** | `_power_grid_peak_tariff` | `_period_cost` |
| Cost Increase Estimate | **Cost Increase Forecast** | `_cost_increase_estimate` | `_cost_increase_forecast` |
| Interval Consumption Estimate | **Interval Consumption Forecast** | `_interval_consumption_estimate` | `_interval_consumption_forecast` |
| Daily Peak *(averaging mode only)* | **Daily Peak Average** | `_daily_peak` | `_daily_peak_average` |
| Forecast Margin | **Target Headroom** | `_forecast_margin` | `_target_headroom` |
| Running Average | **Period Average** | `_running_average` | `_period_average` |
| Running Peak N | **Period Peak N** | `_running_peak_N` | `_period_peak_N` |
| *(internal)* | **Target Headroom** | `_estimation_relative_to_target` | `_target_headroom` |
| *(internal)* | **Target Usage Percentage** | `_estimation_percentage_of_target` | `_target_usage_percentage` |

**How to find old entities:** Settings → Devices & Services → Peak Monitor → Entities, then filter by "unavailable".

### ⚠️ Target Headroom — inverted sign convention

The old **Forecast Margin** sensor reported `estimated − target`: a **negative** value meant you were safely below target, and a **positive** value meant you were exceeding it.

The new **Target Headroom** sensor reports `target − estimated`: a **positive** value means headroom to spare (safe), and a **negative** value means you are on track to exceed target. This aligns the sign convention with the Immediate Headroom and Safe Headroom sensors, where positive always means room available.

**If you have automations or alerts that trigger on this sensor, you must update them:**

| Old trigger (Forecast Margin) | New trigger (Target Headroom) |
|---|---|
| `above: 0` — consumption exceeds target | `below: 0` — consumption exceeds target |
| `below: 0` — consumption below target | `above: 0` — consumption below target |

---

## Bug fixes and behaviour improvements

Minor bug fixes and behaviour fixes, including improved restart resilience for power sensor inputs and more accurate timestamp display on sensor attributes.

**Logo and Icon** — Added a logo and icon, compatible with Home Assistant 2026.3.0 and later.

---

## How to upgrade

1. In HACS, find Peak Monitor and click **Update**
2. Restart Home Assistant
3. Check for unavailable entities and update dashboards or automations using the renamed entity IDs listed above

---

*Full technical changelog: [CHANGELOG.md](CHANGELOG.md)*  
*Sensor reference: [docs/REFERENCE.md](docs/REFERENCE.md)*

