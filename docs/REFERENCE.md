# Sensor Reference — Peak Monitor 2026.4.0

This document describes every sensor created by the Peak Monitor integration: what it shows, when it is created, whether it is enabled by default, and which attributes it exposes.

## Table of Contents

- [Visibility overview](#visibility-overview)
- [Core sensors](#core-sensors)
  - [Period Average](#period-average)
  - [Target](#target)
  - [Target Headroom](#target-headroom)
  - [Status](#status)
- [Conditional sensors](#conditional-sensors)
  - [Daily Peak / Daily Peak Average](#daily-peak--daily-peak-average)
  - [Period Cost](#period-cost)
  - [Cost Increase Forecast](#cost-increase-forecast)
  - [Interval Consumption Forecast](#interval-consumption-forecast)
  - [Interval Consumption](#interval-consumption)
- [Disabled by default](#disabled-by-default)
  - [Estimation Percentage of Target](#estimation-percentage-of-target)
  - [Period Peak N](#period-peak-n)
- [Averaging mode sensors](#averaging-mode-sensors-daily_peaks_averaged--1)
  - [Daily Sub-Peak N](#daily-sub-peak-n)
  - [Immediate Headroom](#immediate-headroom)
  - [Safe Headroom](#safe-headroom)
- [Understanding the sensors](#understanding-the-sensors)

---

## Visibility overview

| Sensor | Always created | Enabled by default | Condition for creation |
|---|:---:|:---:|---|
| Period Average | ✓ | ✓ | — |
| Target | ✓ | ✓ | — |
| Target Headroom | ✓ | ✓ | — |
| Status | ✓ | ✓ | — |
| Daily Peak | — | Yes | Averaging mode is off |
| Daily Peak Average | — | yes | Averaging mode |
| Period Cost | — | ✓ | Price per kW > 0 |
| Cost Increase Forecast | — | ✓ | Price per kW > 0 |
| Interval Consumption Forecast | — | ✓ | No external estimation sensor |
| Interval Consumption | — | ✓ | Cumulative sensor, multiple-peaks mode, or power input |
| Estimation Percentage of Target | ✓ | **No** | — |
| Period Peak N | ✓ | **No** | — (one per configured peak) |
| Daily Sub-Peak N | — | **No** | Averaging mode (daily_peaks_averaged > 1) |
| Immediate Headroom | — | ✓ | Averaging mode |
| Safe Headroom | — | ✓ | Averaging mode |

---

## Core sensors

These sensors are created for every installation and are enabled by default.

---

### Period Average

**Entity ID:** `sensor.{name}_period_average`  
**Unit:** W or kW (matches output unit setting)  
**State class:** Measurement  
**Device class:** Power  

Your current tariff level — the average of your top N interval peaks this month. This is the number that determines your monthly capacity fee.

**How it is calculated:**

The integration tracks the N highest interval consumptions for the month. The period average is the mean of those N values. When a new peak exceeds the current lowest tracked peak, the list is updated and the average recalculates immediately.

```
Tracking top 3 peaks:
Month peaks: [5200, 4800, 4500]  →  Period Average = 4833 W
New interval at 4600 W — does not displace 4500, average stays at 4833 W
New interval at 5400 W — displaces 4500:  [5400, 5200, 4800]  →  average = 5133 W
```

**Attributes:**

| Attribute | Description |
|---|---|
| `period_peak_1`, `period_peak_2`, … | Individual peak values, highest first |
| `period_peak_1_is_today`, … | `true` when that slot belongs to today's daily peak |
| `includes_today` | Whether today's peak is included in the average |
| `last_updated` | Timestamp of the last peak list change (rounded to minute) |
| `price` | Current monthly tariff cost in your currency *(only if price per kW is configured)* |
| `price_unit` | Currency code, e.g. `SEK` |

---

### Target

**Entity ID:** `sensor.{name}_target`  
**Unit:** W or kW  
**State class:** Measurement  
**Device class:** Power  

The recommended consumption ceiling for the current interval. Stay below this to avoid increasing your monthly tariff.

The target is updated at each interval boundary. Its meaning depends on the mode:

**Standard mode (daily_peaks_averaged = 1):**

```
Target = max(daily_peak, lowest_monthly_peak)
```

**Averaging mode (daily_peaks_averaged = N) — three cases:**

*Case A — no sub-peak qualifies yet:*  
Target = lowest monthly peak.

*Case B — some sub-peaks qualify, but today's average is still below the monthly floor:*  
Target = N × lowest_monthly − sum(top N−1 sub-peaks), clamped ≥ smallest sub-peak.

*Case C — today's average already equals or exceeds the floor:*  
Target = smallest committed sub-peak (the weakest slot, which can still be improved).

```
Examples (N=3, lowest monthly peak = 1600 W):
Case A: sub-peaks = [1400, 1200, 1000]  →  Target = 1600
Case B: sub-peaks = [1800, 1500, 1200]  →  T = 3×1600 − (1800+1500) = 1500
Case C: sub-peaks = [2200, 1800, 1500], avg = 1833 > 1600  →  Target = 1500
```

**Attributes:**

| Attribute | Description |
|---|---|
| `peak_last_updated` | Timestamp of last target recalculation (rounded to minute) |

---

### Target Headroom

**Entity ID:** `sensor.{name}_target_headroom`  
**Unit:** W or kW  
**State class:** Measurement  
**Device class:** Power  

How much room remains between your current projected interval consumption and the target — phrased as remaining capacity, consistent with the other headroom sensors.

```
Target Headroom = Target − Estimated Interval Consumption
```

**Positive** = below target (safe — headroom to spare). **Negative** = on track to exceed target and form a new peak.

> **Note for users upgrading from 2026.3:** The sign convention is **inverted** compared to the old "Forecast Margin" sensor. Automations that previously triggered `above: 0` (exceeding target) must be updated to trigger `below: 0`.

Becomes unavailable when the input consumption sensor is unavailable.

---

### Status

**Entity ID:** `sensor.{name}_status`  
**Unit:** — (text)  
**Device class:** Enum  
**Possible states:** `inactive` · `reduced` · `active`  

Current state of the tariff system.

| State | Meaning |
|---|---|
| `active` | Tariff is fully active; consumption is tracked and peaks are updated |
| `reduced` | Tariff is active at a reduced rate (e.g. night hours, weekend with reduced setting) |
| `inactive` | Tariff is off; consumption is not counted toward peaks |

**Attributes:**

| Attribute | When | Description |
|---|---|---|
| `inactive_reason` | State = inactive | Why the tariff is off |
| `reduced_reason` | State = reduced | Why the tariff is reduced |

Possible reason values: `external_mute` · `excluded_month` · `holiday` · `weekend` · `time_of_day`

---

## Conditional sensors

These sensors are only created when specific configuration options are active.

---

### Daily Peak / Daily Peak Average

**Entity ID:** `sensor.{name}_daily_peak` (standard) or `sensor.{name}_daily_peak_average` (averaging mode)  
**Unit:** W or kW  
**State class:** Measurement  
**Device class:** Power  
**Created when:** *Only one peak per day* is enabled  
**Enabled by default:** No — must be enabled manually in the entity registry  

Today's peak value that will be committed to the monthly peaks list at midnight.

In standard mode this is the single highest interval reading seen today during active tariff hours. In averaging mode (`daily_peaks_averaged > 1`) this is the **average of the N highest intra-day interval readings** committed so far.

**Attributes:**

| Attribute | Description |
|---|---|
| `peak_last_updated` | Timestamp when the peak last changed (rounded to minute) |
| `averaging_model` | e.g. `"avg of 2 highest peaks per day"` *(averaging mode only)* |
| `sub_peak_1`, `sub_peak_2`, … | Individual sub-peak values *(averaging mode only)* |

---

### Period Cost

**Entity ID:** `sensor.{name}_period_cost`  
**Unit:** Your configured currency (e.g. SEK)  
**State class:** Total  
**Device class:** Monetary  
**Created when:** *Price per kW* > 0  

Estimated total monthly capacity fee based on the current period average and your configured pricing.

```
Period Cost = Fixed Monthly Fee + (Price per kW × Period Average in kW)

Example:
Period Average = 4833 W = 4.833 kW
Price per kW    = 47.5 SEK
Fixed fee       = 522 SEK
Period Cost     = 522 + (47.5 × 4.833) = 751.57 SEK
```

**Attributes:**

| Attribute | Description |
|---|---|
| `includes_today` | Whether today's peak is included in the calculation |
| `peak_last_updated` | Timestamp of the last peak change that affected this value (rounded to minute) |

---

### Cost Increase Forecast

**Entity ID:** `sensor.{name}_cost_increase_forecast`  
**Unit:** Your configured currency (e.g. SEK)  
**State class:** Measurement  
**Device class:** Monetary  
**Created when:** *Price per kW* > 0  

Real-time estimate of how much your monthly bill would increase if the current interval ends as a new peak. Shows 0 when you are at or below target.

```
If estimated consumption > target:
  New peaks list = current peaks updated with estimated consumption
  Cost Increase = (New Average − Old Average) / 1000 × Price per kW

Example:
Current peaks: [5200, 4800, 4500], average = 4833 W
Estimated this interval: 5500 W
New peaks: [5500, 5200, 4800], new average = 5167 W
Increase = (5167 − 4833) / 1000 × 47.5 = 15.87 SEK/month
```

---

### Interval Consumption Forecast

**Entity ID:** `sensor.{name}_interval_consumption_forecast`  
**Unit:** W or kW  
**State class:** Measurement  
**Device class:** Power  
**Created when:** No external estimation sensor is configured  

Built-in projection of total interval consumption based on consumption so far and time elapsed. This value feeds the Target, Target Headroom, Percentage, and cost sensors.

The estimate blends the current rate of consumption with the previous interval's rate, becoming progressively more stable as the interval progresses.

---

### Interval Consumption

**Entity ID:** `sensor.{name}_interval_consumption`  
**Unit:** Wh or kWh  
**State class:** Total increasing (resets each interval)  
**Created when:** Input sensor is cumulative, multiple-peaks-per-day mode is active, or input is a power sensor (W/kW)  

Consumption accumulated during the current interval, derived from your input sensor.

- Cumulative energy sensor: `current reading − reading at interval start`  
- Power sensor (W/kW): trapezoidal integral of instantaneous power readings

---

## Disabled by default

These sensors are created for every installation but are hidden in the entity registry. Enable them individually in Settings → Devices & Services → Peak Monitor → Entities.

---

### Estimation Percentage of Target

**Entity ID:** `sensor.{name}_target_usage_percentage`  
**Unit:** %  
**State class:** Measurement  
**Enabled by default:** No  

Estimated interval consumption as a percentage of target. Below 100% is safe; above 100% means a new peak is forming. Disabled per default as it is a hard sensor to use for automation. 90 % can give vastly different implication early and late in the period.

```
Percentage = (Estimated Consumption / Target) × 100
```

Useful for gauge cards. Becomes unavailable when the input sensor is unavailable.

---

### Period Peak N

**Entity ID:** `sensor.{name}_period_peak_1`, `_period_peak_2`, …  
**Unit:** W or kW  
**State class:** Measurement  
**Device class:** Power  
**Enabled by default:** No (one per configured peak, all hidden)  

Individual monthly peak values ranked highest to lowest. The same information is available as attributes on the Period Average sensor and most significant information is accessible with target and other sensors, so these sensors are disabled by default.

Enable when you want to graph individual peaks, build per-peak automations, or compare slots over time.

**Attributes:**

| Attribute | Description |
|---|---|
| `peak_last_updated` | Timestamp of the last change to the peaks list (rounded to minute) |

---

## Averaging mode sensors (daily_peaks_averaged > 1)

Created only when *Daily Peak Averaging* is set to 2 or more. All are enabled by default when present.

---

### Daily Sub-Peak N

**Entity ID:** `sensor.{name}_daily_sub_peak_1`, `_daily_sub_peak_2`, …  
**Unit:** W or kW  
**State class:** Measurement  
**Device class:** Power  
**Enabled by default:** No

One sensor per sub-peak slot. Shows the individual interval readings that contribute to today's averaged daily peak, ranked highest to lowest. Updated at each interval boundary. Disabled per default, with same motivation as for Period Peak N sensors.

```
Example (daily_peaks_averaged = 2):
08:00–09:00 → 5000 W  →  daily_sub_peak_1 = 5000
14:00–15:00 → 4200 W  →  daily_sub_peak_2 = 4200
Daily Peak Average = (5000 + 4200) / 2 = 4600 W
```

**Attributes:**

| Attribute | Description |
|---|---|
| `peak_last_updated` | Timestamp of the last sub-peak change (rounded to minute) |
| `rank` | Position (1 = highest) |

---

### Immediate Headroom

**Entity ID:** `sensor.{name}_immediate_headroom`  
**Unit:** W or kW  
**State class:** Measurement  
**Device class:** Power  
**Available when:** Tariff is active and averaging mode is configured

The absolute maximum consumption you can reach this interval without adding any extra cost to your monthly bill.

This is a hard ceiling. **Target** is the recommended operating point that keeps you safe across the whole day. Use Immediate Headroom when you need to know the safe ceiling for a single high-draw event (EV charging, oven, sauna).

> **Warning:** Consuming up to headroom every interval early in the day will rapidly fill all sub-peak slots with large values. Once committed, target drops and there is little room left. Generally aim for Target, not Headroom.

```
H = N × lowest_period_peak − sum(top N−1 committed sub-peaks)
H = max(H, smallest_committed_sub_peak)

Example (N=2, lowest monthly peak = 2000 W, sub-peaks = [1800]):
H = 2×2000 − 1800 = 2200 W
```

Target is always ≤ Immediate Headroom.

**Attributes:**

| Attribute | Description |
|---|---|
| `n_sub_peaks` | Configured N |
| `lowest_monthly_peak` | Monthly floor in output unit |
| `sub_peaks` | Committed sub-peak values, highest first |
| `top_n_minus_1_sum` | Sum of top N−1 sub-peaks |

---

### Safe Headroom

**Entity ID:** `sensor.{name}_safe_headroom`  
**Unit:** W or kW  
**State class:** Measurement  
**Device class:** Power  
**Available when:** Tariff is active and averaging mode is configured

The guaranteed-safe operating level: the consumption value below which no remaining interval today can worsen any sub-peak slot or increase the monthly average.

```
Safe Headroom = min(committed daily sub-peaks)
```

As long as every remaining interval stays below Safe Headroom, the weakest sub-peak slot is not displaced and the monthly average cannot worsen.

Use Safe Headroom in automations that must guarantee they never increase the monthly bill, such as smart EV chargers or hot water heaters. For daily planning use Target; for the hard ceiling use Immediate Headroom; for guaranteed-safe automation use Safe Headroom.

**Attributes:**

| Attribute | Description |
|---|---|
| `n_sub_peaks` | Configured N |
| `sub_peaks` | Committed sub-peak values, highest first |
| `smallest_sub_peak` | The value used as safe headroom |

---

## Understanding the sensors

### Data flow

```
┌───────────────────────────────┐
│  Input sensor                 │
│  Wh/kWh (energy) or W/kW      │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  Interval Consumption         │  Wh accumulated this interval
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  Interval Consumption         │  Projected Wh at end of interval
│  Forecast / external sensor   │
└───────────┬───────────────────┘
            │
     ┌──────┴────────┐
     ▼               ▼
┌──────────┐  ┌─────────────────────────────┐
│  Target  │  │  Target Headroom            │
└──────────┘  │  Cost Increase Forecast     │
              │  Estimation Percentage      │
              └─────────────────────────────┘
                │
                ▼  at interval boundary
┌───────────────────────────────┐
│  Daily Peak                   │
│  (or Daily Sub-Peaks +        │
│   headroom sensors)           │
└───────────────┬───────────────┘
                │  at midnight
                ▼
┌───────────────────────────────┐
│  Period Peaks  (top N)       │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  Period Average              │
│  Period Cost                  │
└───────────────────────────────┘
```

### Update frequency

| Sensor | Updates when |
|---|---|
| Interval Consumption Forecast | Every input sensor update |
| Target Headroom | Every input sensor update |
| Estimation Percentage | Every input sensor update |
| Cost Increase Forecast | Every input sensor update |
| Target | At each interval boundary |
| Immediate / Safe Headroom | At each interval boundary |
| Daily Sub-Peak N | At each interval boundary |
| Daily Peak | At each interval boundary (when a new high is reached) |
| Period Average | When a peak is committed (typically midnight) |
| Period Cost | When Period Average changes |
| Period Peak N | When Period Average changes |
| Status | On schedule change (hour, day, holiday, month) |

### Data persistence

The integration stores the following between restarts:

- Monthly peaks list
- Daily peak (and sub-peaks in averaging mode)
- Interval consumption accumulated so far *(restored when restarting within the same interval)*
- Last peak timestamps
- Cumulative sensor baseline value

Data is stored in `.storage/peak_monitor_data_{entry_id}`.

### When sensors show Unknown or Unavailable

**Unknown:** The integration just started and has not yet processed a sensor reading. Resolves within one interval.

**Unavailable (Target Headroom, Percentage, Cost Increase):** The input consumption sensor is currently unavailable. Check the sensor entity and its integration.

**Target = 0 or unavailable:** Tariff is currently inactive. Check the Status sensor.

---

## Input sensor types

### Energy sensors (Wh / kWh) — recommended

Energy sensors report accumulated consumption. They are more resilient to Home Assistant restarts because the energy value at restart reflects actual consumption even if HA was offline during that period, given data is gathered from an energy meter and not calculated from power sensor.

### Power sensors (W / kW) — usable with caveats

Power sensors report instantaneous draw. The integration integrates readings over time using trapezoidal integration. Accumulated consumption during gaps (HA offline, sensor unavailable) is not counted.

The integration correctly restores accumulated interval consumption across same-interval restarts, but any gap in readings during that interval is lost.

> **Recommendation:** Use an energy sensor whenever possible.

---

## Reset Peak service

**Service:** `peak_monitor.reset_peak`

Manually reset one or all period peaks.

| Parameter | Required | Default | Description |
|---|:---:|---|---|
| `peak_index` | No | All peaks | 1-based index of the peak to reset (1 = highest) |
| `reset_value` | No | Configured reset value | Value to reset to; clamped if higher than the current peak |

Period average and all price indicators recalculate immediately after the call.

---

## Automation examples

### Alert when approaching limit

```yaml
automation:
  - alias: "Peak Monitor Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.peak_monitor_target_usage_percentage
        above: 90
    condition:
      - condition: state
        entity_id: sensor.peak_monitor_status
        state: "active"
    action:
      - service: notify.mobile_app
        data:
          message: >
            Power at {{ states('sensor.peak_monitor_target_usage_percentage') | round }}%
            of target ({{ states('sensor.peak_monitor_target') }} W limit).
```

### Stop EV charging when above target

```yaml
automation:
  - alias: "Stop EV Charging Above Target"
    trigger:
      - platform: numeric_state
        entity_id: sensor.peak_monitor_target_headroom
        below: 0
    condition:
      - condition: state
        entity_id: sensor.peak_monitor_status
        state: "active"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.ev_charger
```

### Safe EV charging using Safe Headroom (averaging mode)

```yaml
automation:
  - alias: "Allow EV charge if safe headroom permits"
    trigger:
      - platform: time_pattern
        minutes: "/5"
    condition:
      - condition: state
        entity_id: sensor.peak_monitor_status
        state: "active"
      - condition: numeric_state
        entity_id: sensor.peak_monitor_safe_headroom
        above: 3500
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.ev_charger
```
