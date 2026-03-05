# Installation Guide for Peak Monitor Integration

This guide provides detailed instructions for installing and configuring the Peak Monitor integration for Home Assistant.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Installation Methods](#installation-methods)
3. [Configuration](#configuration)
4. [Sensor Setup](#sensor-setup)
5. [Troubleshooting](#troubleshooting)

## Prerequisites

Before installing the Peak Monitor integration, ensure you have:

- Home Assistant (minimum version 2024.6.0 or later recommended)
- A consumption sensor that tracks your power consumption
  - This can be either:
    - **Hourly resetting sensor**: Resets to 0 at the start of each hour
    - **Cumulative sensor**: Continuously increasing value (e.g., total kWh)
- (Optional) An estimation/prediction sensor for the current hour's consumption

## Installation Methods

### Method 1: HACS (Recommended)

HACS (Home Assistant Community Store) is the easiest way to install and update custom integrations.

#### Step 1: Install HACS
If you haven't installed HACS yet:
1. Follow the official HACS installation guide at https://hacs.xyz/docs/setup/download
2. Restart Home Assistant after installation

#### Step 2: Add Peak Monitor Repository
1. Open Home Assistant
2. Go to **HACS** → **Integrations**
3. Click the **three dots menu** (⋮) in the top right corner
4. Select **Custom repositories**
5. Add the repository URL: `https://github.com/krogell/peak-monitor`
6. Select category: **Integration**
7. Click **Add**

#### Step 3: Install Peak Monitor
1. In HACS → Integrations, search for "Peak Monitor"
2. Click on **Peak Monitor** in the search results
3. Click **Download** (or **Install** in older HACS versions)
4. Select the version you want to install (latest is recommended)
5. Click **Download**

#### Step 4: Restart Home Assistant
1. Go to **Settings** → **System** → **Restart**
2. Click **Restart** and wait for Home Assistant to come back online

### Method 2: Manual Installation

If you prefer manual installation or don't use HACS:

#### Step 1: Download the Integration
1. Download the latest release from the GitHub repository
2. Extract the ZIP file to a temporary location

#### Step 2: Copy Files to Home Assistant
1. Connect to your Home Assistant installation (via SSH, Samba, or file browser)
2. Navigate to your Home Assistant configuration directory (usually `/config/`)
3. If it doesn't exist, create a `custom_components` directory:
   ```bash
   mkdir -p /config/custom_components
   ```
4. Copy the `peak_monitor` folder from the extracted ZIP into `/config/custom_components/`
   - The final path should be: `/config/custom_components/peak_monitor/`

#### Step 3: Verify Installation
Your directory structure should look like this:
```
/config/
├── custom_components/
│   └── peak_monitor/
│       ├── __init__.py
│       ├── config_flow.py
│       ├── const.py
│       ├── holidays.py
│       ├── manifest.json
│       ├── sensor.py
│       ├── strings.json
│       ├── utils.py
│       └── translations/
│           ├── en.json
│           └── sv.json
```

#### Step 4: Restart Home Assistant
1. Go to **Settings** → **System** → **Restart**
2. Click **Restart** and wait for Home Assistant to come back online

## Configuration

After installation and restart, you can configure the integration:

### Step 1: Add Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration** (bottom right)
3. Search for "Peak Monitor"
4. Click on **Peak Monitor** to start configuration

### Step 2: Basic Configuration

You will be presented with a configuration form. Here's what each field means:

#### Required Settings

**Name**
- Default: "Peak Monitor"
- Description: A friendly name for this integration instance
- You can have multiple instances with different names

**Consumption Sensor**
- Required: Yes
- Description: The entity that measures your power consumption
- Example: `sensor.electricity_consumption`
- This sensor provides the actual consumption data used to calculate peaks

**Sensor Resets Every Hour**
- Default: No (unchecked)
- Description: How your consumption sensor behaves:
  - **Checked (Yes)**: Sensor resets to 0 at the start of each hour
  - **Unchecked (No)**: Sensor is cumulative (always increasing)
- Choose based on your sensor's actual behavior

#### Optional Settings

**Estimation Sensor**
- Required: No (can be left empty)
- Description: An external sensor that estimates the current hour's consumption
- Example: `sensor.power_consumption_prediction`
- Leave empty to use the built-in internal estimation
- If provided, this will be used instead of internal estimation

**Price per kW**
- Default: 0
- Description: The price you pay per kW of power (for the tariff portion). Set to your actual network rate.
- Used to calculate the monthly cost sensor

**Fixed Monthly Fee**
- Default: 0
- Description: Fixed monthly fee from your electricity provider. Set to your actual standing charge (or keep it at 0 to only track your variable cost).
- Added to the tariff cost to calculate total monthly grid fee

### Step 3: Tariff Schedule Configuration

**Active Start Hour**
- Default: 6 (06:00)
- Description: Hour when power tariff monitoring begins each day
- Range: 0-23

**Active End Hour**
- Default: 21 (21:00)
- Description: Hour when power tariff monitoring ends each day
- Range: 0-23
- Note: The end hour is exclusive (tariff stops at this hour)

**Active Months**
- Default: November, December, January, February, March
- Description: Which months the tariff is active
- Select all months where you want peak tracking enabled

**Number of Peaks**
- Default: 3
- Range: 1-10
- Description: How many running peaks are used to calculate the tariff
- Common Swedish tariffs use 3 peaks (average of top 3 hours)

### Step 4: Holiday and Weekend Configuration

**Holidays to Exclude**
- Default: Official holidays
- Description: Swedish holidays where tariff should not apply
- Options include:
  - Official holidays (includes all major Swedish holidays)
  - Individual holiday eves (Julafton, Nyårsafton, etc.)

**Holiday Behavior**
- Default: No tariff
- Options:
  - **No tariff**: Holidays are completely excluded from tariff
  - **Reduced tariff**: Holidays use the reduced tariff rate

**Weekend Behavior**
- Default: No tariff
- Options:
  - **No tariff**: Weekends are completely excluded from tariff
  - **Reduced tariff**: Weekends use the reduced tariff rate
  - **Full tariff**: Weekends are treated like weekdays

### Step 5: Reduced Tariff Configuration (Optional)

**Daily Reduced Tariff Enabled**
- Default: No (unchecked)
- Description: Enable a reduced tariff rate for certain hours of the day
- Common use: Night hours or off-peak times

**Reduced Start Hour**
- Default: 22 (22:00)
- Description: Hour when reduced tariff begins
- Only used if Daily Reduced Tariff is enabled

**Reduced End Hour**
- Default: 6 (06:00)
- Description: Hour when reduced tariff ends
- Only used if Daily Reduced Tariff is enabled

**Reduced Factor**
- Default: 0.5 (50%)
- Range: 0.0 to 1.0
- Description: Multiplication factor for consumption during reduced hours
- Example: 0.5 means consumption counts as 50% of actual value

### Step 6: Advanced Settings

**Reset Value**
- Default: 500 Wh
- Description: Initial value for peaks when month resets
- Prevents zero values in monthly averages

### Step 7: Complete Configuration

1. Review all settings
2. Click **Submit** to save the configuration
3. The integration will create several sensor entities

## Sensor Setup

After configuration, the integration creates several sensors:

### Main Sensors

1. **Peak Monitor** (`sensor.peak_monitor`)
   - Shows the current tariff (average of top peaks)
   - Unit: Wh
   - Attributes include individual peak values

2. **Peak Monitor Target** (`sensor.peak_monitor_target`)
   - The target consumption to avoid increasing your tariff
   - Updates hourly based on remaining time in month

3. **Peak Monitor Relative** (`sensor.peak_monitor_relative`)
   - Difference between estimated and target consumption
   - Positive = above target, Negative = below target

4. **Power Grid Peak Tariff** (`sensor.monthly_power_grid_fee`)
   - Estimated monthly cost in SEK
   - Includes both tariff and fixed fee

5. **Cost Increase Estimate** (`sensor.estimated_cost_increase_estimate`)
   - Real-time estimate of cost increase if consumption exceeds target
   - Unit: SEK

6. **Peak Monitor Estimation Percentage of Target** (`sensor.peak_monitor_percentage_of_target`)
   - Estimation as percentage of target
   - Useful for automations

7. **Peak Monitor** (state sensor) (`sensor.peak_monitor_2`)
   - Shows tariff state: inactive, reduced, or active
   - Useful for automations and visual indicators

8. **Peak Monitor Daily Peak** (`sensor.peak_monitor_daily_peak`)
   - Today's highest consumption hour
   - Resets at midnight

### Conditional Sensors

9. **Interval Consumption Estimate** (`sensor.current_hour_estimation`)
   - Only created if no external estimation sensor is configured
   - Shows the built-in prediction for interval consumption estimate

10. **This Interval Consumption** (`sensor.this_hour_consumption`)
    - Only created if consumption sensor is cumulative (doesn't reset)
    - Shows consumption for the current hour
    - Automatically resets at each hour boundary

11. **Peak Monitor Peak 1, 2, 3...** (`sensor.peak_monitor_peak_1`, etc.)
    - Individual monthly peak sensors
    - Hidden by default (can be enabled in entity settings)
    - Number of sensors equals "Number of Peaks" setting

### Using Sensors in Automations

Example automation to send notification when approaching target:

```yaml
automation:
  - alias: "Peak Monitor Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.peak_monitor_percentage_of_target
        above: 95
    action:
      - service: notify.mobile_app
        data:
          message: "Warning: Approaching power consumption target ({{ states('sensor.peak_monitor_percentage_of_target') }}%)"
```

Example using the state sensor:

```yaml
automation:
  - alias: "Tariff Active Indicator"
    trigger:
      - platform: state
        entity_id: sensor.peak_monitor_2
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

## Troubleshooting

### Integration Not Found After Installation

**Solution:**
1. Verify files are in the correct location: `/config/custom_components/peak_monitor/`
2. Check that `manifest.json` exists in the folder
3. Restart Home Assistant again
4. Clear browser cache (Ctrl+F5 or Cmd+Shift+R)
5. Check Home Assistant logs for errors: **Settings** → **System** → **Logs**

### Sensors Show "Unavailable" or "Unknown"

**Possible Causes:**
1. **Consumption sensor is unavailable**
   - Check that your consumption sensor is working
   - Go to **Developer Tools** → **States** and search for your sensor

2. **Invalid sensor configuration**
   - Verify the consumption sensor entity ID is correct
   - Ensure the sensor provides numeric values

3. **Tariff is inactive**
   - Some sensors (like percentage) only show values when tariff is active
   - Check if current time/day/month is within active periods
   - Check the "Peak Monitor" state sensor to see if it shows "inactive"

**Solution:**
- Reconfigure the integration: **Settings** → **Devices & Services** → **Peak Monitor** → **Configure**
- Check logs for specific error messages

### Estimation Sensor Shows No Data

The internal estimation sensor should show data even when the tariff is inactive. If it still shows unavailable:

**Solution:**
1. Ensure you haven't configured an external estimation sensor
   - If you have, the internal sensor won't be created
2. Verify consumption sensor is providing data
3. Wait for at least one consumption update after the hour starts

### Peaks Not Updating

**Check:**
1. Is the current hour within active hours? (default 6-21)
2. Is today within active months? (default Nov-Mar)
3. Is it a weekend or holiday when those are excluded?
4. Check consumption sensor is updating correctly
5. Look at "Peak Monitor Daily Peak" - is it updating?

**Solution:**
- Review your active hours, months, holiday, and weekend settings
- Check that consumption sensor is working
- Verify "Sensor Resets Every Hour" setting matches your sensor's behavior

### Incorrect Cost Calculations

**Check:**
1. Verify "Price per kW" setting (default 0 — set to your actual network rate)
2. Verify "Fixed Monthly Fee" setting (default 0 — set to your actual standing charge)
3. Check that consumption values look correct
4. Verify "Input Unit" matches your sensor (Wh vs kWh)

**Solution:**
- Reconfigure with correct pricing: **Settings** → **Devices & Services** → **Peak Monitor** → **Options**
- Update "Input Unit" if your sensor reports in kWh but you selected Wh (or vice versa)

### Cumulative Sensor Mode Issues

If using a cumulative (non-resetting) sensor:

**Symptoms:**
- Consumption jumps at unexpected times
- "This Interval Consumption" shows wrong values

**Solution:**
1. Ensure "Sensor Resets Every Hour" is **unchecked**
2. If your sensor resets monthly, this is normal - the integration handles it
3. Check Home Assistant logs for "Cumulative sensor reset detected" messages
4. After a sensor reset, wait for one full hour for accurate data

### Running Peaks Not Resetting

**Expected Behavior:**
- Peaks reset on the 1st of each month at midnight

**If peaks don't reset:**
1. Check Home Assistant was running at midnight on the 1st
2. Check logs for any errors during reset

**Manual Reset:**
You can manually reset by removing and re-adding the integration (data will be lost).


## Getting Help

If you encounter issues not covered here:

1. **Check the logs**
   - Go to **Settings** → **System** → **Logs**
   - Look for entries starting with `custom_components.peak_monitor`

2. **Enable debug logging**
   Add to `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.peak_monitor: debug
   ```
   Restart Home Assistant and reproduce the issue

3. **Report an issue**
   - Visit: https://github.com/krogell/peak-monitor/issues
   - Provide:
     - Home Assistant version
     - Peak Monitor version
     - Relevant log entries
     - Your configuration (remove sensitive data)
     - Steps to reproduce

## Updating the Integration

### Via HACS

1. Go to **HACS** → **Integrations**
2. Find **Peak Monitor** in your installed integrations
3. If an update is available, you'll see an "Update" button
4. Click **Update**
5. Restart Home Assistant

### Manual Update

1. Download the new version
2. Extract and replace the files in `/config/custom_components/peak_monitor/`
3. Restart Home Assistant
4. Check release notes for any breaking changes or required reconfiguration
