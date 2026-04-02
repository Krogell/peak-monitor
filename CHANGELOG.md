# Changelog

## 2026.4.0

Changes relative to 2026.3.

### New features

- **Averaging of daily peak** Configure N numbers of peak, daily peak is the average of the N highest peaks.
- **Power input** In addition to consumption input (Wh/kWh), current power (W/kW) is now accepted.
- **Configurable interval length** Change the length of your peak monitor intervals.
- **Configurable reset schedule** Choose wether you want to reset peaks every new week, month, or not at all.
- **Reset peaks service** Reset all, or any specific peak, from an automation.
- **Configurable currency** Now you can get the period cost in any currency.

### New sensors

- **Safe Headroom** (averaging mode only) — shows the consumption level that is guaranteed not to worsen any sub-peak slot for the rest of the day. Equals `min(committed daily sub-peaks)`. Useful for automations that must never increase the monthly bill.
- **Immediate Headroom** (averaging mode only) — shows the highest consumption level that will not increase your bill for now. But using this unvisely can put you in a bad spot for later in the day.

### Renamed sensors

The following sensors have new names. Home Assistant will treat them as new entities; your old entities may become unavailable. Re-add them to any dashboards or automations after upgrading.

| Old name | New name | Entity ID change |
|---|---|---|
| Power Grid Peak Tariff | **Period Cost** | `_power_grid_peak_tariff` → `_period_cost` |
| Cost Increase Estimate | **Cost Increase Forecast** | `_cost_increase_estimate` → `_cost_increase_forecast` |
| Interval Consumption Estimate | **Interval Consumption Forecast** | `_interval_consumption_estimate` → `_interval_consumption_forecast` |
| Daily Peak *(averaging mode)* | **Daily Peak Average** | `_daily_peak` → `_daily_peak_average` |
| Running Average | **Period Average** | `_running_average` → `_period_average` |
| Running Peak N | **Period Peak N** | `_running_peak_N` → `_period_peak_N` |
| *(internal)* | **Target Headroom** | `_estimation_relative_to_target` → `_target_headroom` |
| *(internal)* | **Target Usage Percentage** | `_estimation_percentage_of_target` → `_target_usage_percentage` |


### UI and branding

- Brand icons added (`brands/icon.png` and `brands/icon@2x.png`) for display in the Home Assistant UI integration list.


# Peak Monitor 2026.3 — Release Notes

This is the first public release
