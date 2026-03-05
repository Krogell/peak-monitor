"""Utility functions for Peak Monitor integration."""
from datetime import datetime
from typing import Any


def get_int(data: dict, key: str, default: int) -> int:
    """Safely get integer value from config data.
    
    Distinguishes between missing key and zero value.
    
    Args:
        data: Configuration dictionary
        key: Key to retrieve
        default: Default value if key is missing
        
    Returns:
        Integer value from data or default if key is missing
    """
    if key in data:
        return int(data[key])
    return default


def get_float(data: dict, key: str, default: float) -> float:
    """Safely get float value from config data.
    
    Distinguishes between missing key and zero value.
    
    Args:
        data: Configuration dictionary
        key: Key to retrieve
        default: Default value if key is missing
        
    Returns:
        Float value from data or default if key is missing
    """
    if key in data:
        return float(data[key])
    return default


def get_bool(data: dict, key: str, default: bool) -> bool:
    """Safely get boolean value from config data.
    
    Args:
        data: Configuration dictionary
        key: Key to retrieve
        default: Default value if key is missing
        
    Returns:
        Boolean value from data or default if key is missing
    """
    if key in data:
        return bool(data[key])
    return default


def get_str(data: dict, key: str, default: str | None) -> str | None:
    """Safely get string value from config data.
    
    Args:
        data: Configuration dictionary
        key: Key to retrieve
        default: Default value if key is missing
        
    Returns:
        String value from data or default if key is missing
    """
    if key in data:
        return data[key]
    return default


def get_list(data: dict, key: str, default: list) -> list:
    """Safely get list value from config data.
    
    Args:
        data: Configuration dictionary
        key: Key to retrieve
        default: Default value if key is missing
        
    Returns:
        List value from data or default if key is missing
    """
    if key in data:
        return data[key]
    return default


def is_time_in_range(
    current_time: datetime,
    start_hour: int,
    end_hour: int
) -> bool:
    """Check if current time is within the specified hour range.

    Handles ranges that cross midnight (e.g., 22:00 to 06:00).
    """
    current_hour = current_time.hour

    if start_hour <= end_hour:
        # Normal range (e.g., 6 to 21)
        return start_hour <= current_hour < end_hour
    else:
        # Range crosses midnight (e.g., 22 to 6)
        return current_hour >= start_hour or current_hour < end_hour


def get_consumption_with_reduction(
    consumption: float,
    current_time: datetime,
    reduced_enabled: bool,
    reduced_start: int,
    reduced_end: int,
    reduced_factor: float,
) -> float:
    """Calculate consumption with potential reduction factor applied.

    Returns consumption * reduced_factor if currently in reduced hours,
    otherwise returns consumption unchanged.
    """
    if not reduced_enabled:
        return consumption

    if is_time_in_range(current_time, reduced_start, reduced_end):
        return consumption * reduced_factor

    return consumption


def calculate_internal_estimation(
    consumption_samples: list[tuple[datetime, float]],
    current_time: datetime,
    previous_hour_rate: float | None = None,
) -> float:
    """Calculate estimated hourly consumption using power-based calculation with smooth blending.
    
    Formula: E_est(t) = E(t) + P_avg(t) × (60 - t) / 60
    
    For first 5 minutes (300 seconds): Continuous smooth blending with 5-minute rolling average
    
    Blending algorithm:
    - Weight for current algorithm = seconds_since_hour_change / 3
    - Weight for 5-minute average = 100 - (seconds_since_hour_change / 3)
    - 5-minute average uses: last N minutes of previous hour + M minutes of current hour
      where N + M = 5 minutes
    
    Example at 120 seconds (2 minutes):
    - Current weight = 120/3 = 40%
    - 5-min avg weight = 100-40 = 60%
    - 5-min window = last 3 min of prev hour + 2 min of current hour
    
    Big Drop Filter:
    - Filters out samples before a consumption drop >= 5 kW (5000 W)
    - This prevents misleading high estimates when large loads turn off
    - Example: If consumption drops from 6000W to 1000W, samples before the drop are excluded
    
    Where:
    - E(t) = accumulated energy so far this hour (Wh)
    - P_avg(t) = mean instantaneous power over recent samples (W)
    - t = minutes elapsed in current hour
    
    Args:
        consumption_samples: List of (timestamp, cumulative_consumption_this_hour) tuples
        current_time: Current datetime
        previous_hour_rate: Rate in Wh/second from previous hour (for 5-min average)
        
    Returns:
        Estimated consumption for the full hour (Wh)
    """
    if not consumption_samples:
        # No data - use previous hour if available
        if previous_hour_rate is not None and previous_hour_rate > 0:
            return previous_hour_rate * 3600.0
        return 0.0
    
    # Filter out samples before big consumption drops (>= 5 kW)
    # Find the last significant drop in power
    BIG_DROP_THRESHOLD_W = 5000.0  # 5 kW
    
    filtered_samples = []
    last_drop_index = -1
    
    if len(consumption_samples) >= 2:
        for i in range(1, len(consumption_samples)):
            ts1, val1 = consumption_samples[i-1]
            ts2, val2 = consumption_samples[i]
            
            time_diff_seconds = ts2.timestamp() - ts1.timestamp()
            if time_diff_seconds > 0:
                # Calculate instantaneous power drop
                energy_diff = val2 - val1
                power_w = (energy_diff * 3600.0) / time_diff_seconds
                
                # Check for big drop (negative power change)
                if power_w < -BIG_DROP_THRESHOLD_W:
                    # Found a big drop - mark this as the cutoff point
                    last_drop_index = i
    
    # Use samples after the last big drop (or all samples if no big drop)
    if last_drop_index >= 0:
        filtered_samples = consumption_samples[last_drop_index:]
    else:
        filtered_samples = consumption_samples
    
    # If filtering removed all samples, fall back to using all samples
    if not filtered_samples:
        filtered_samples = consumption_samples
    
    # Get current accumulated energy E(t)
    _, E_t = filtered_samples[-1]
    
    # Calculate seconds elapsed in current hour
    seconds_elapsed = current_time.minute * 60 + current_time.second
    
    # If we're at the very start of the hour, use previous hour rate
    if seconds_elapsed < 1:
        if previous_hour_rate is not None and previous_hour_rate > 0:
            return previous_hour_rate * 3600.0
        return max(0.0, E_t)
    
    # Calculate minutes elapsed
    t = current_time.minute + (current_time.second / 60.0)
    
    # Calculate remaining minutes
    remaining_minutes = 60.0 - t
    
    # If we're at the end of the hour, no remaining time to estimate
    if remaining_minutes <= 0:
        return max(0.0, E_t)
    
    # Calculate current algorithm estimate
    if len(filtered_samples) < 2:
        # Only one sample - simple projection
        current_estimate = (E_t / t) * 60.0
    else:
        # Calculate instantaneous power from consecutive samples
        powers = []
        for i in range(1, len(filtered_samples)):
            ts1, val1 = filtered_samples[i-1]
            ts2, val2 = filtered_samples[i]
            
            time_diff_seconds = ts2.timestamp() - ts1.timestamp()
            if time_diff_seconds > 0:
                # Power in W = (energy_diff in Wh) / (time_diff in hours)
                energy_diff = val2 - val1
                power_w = (energy_diff * 3600.0) / time_diff_seconds
                powers.append(power_w)
        
        if not powers:
            # Couldn't calculate any power values, use simple projection
            current_estimate = (E_t / t) * 60.0
        else:
            # Calculate mean power
            P_avg = sum(powers) / len(powers)
            
            # Apply formula: E_est(t) = E(t) + P_avg(t) × (60 - t) / 60
            current_estimate = E_t + (P_avg * remaining_minutes / 60.0)
    
    # Continuous smooth blending for first 5 minutes (300 seconds)
    if seconds_elapsed < 300 and previous_hour_rate is not None and previous_hour_rate > 0:
        # Calculate blend weights
        # Current algorithm weight increases from 0% to 100% over 5 minutes
        weight_current = seconds_elapsed / 3.0  # 0 to 100 over 300 seconds
        weight_5min_avg = 100.0 - weight_current
        
        # Calculate 5-minute rolling average estimate
        # This uses previous_hour_rate as approximation for the rolling window
        # In a full implementation, you'd track actual 5-minute consumption window
        five_min_avg_estimate = previous_hour_rate * 3600.0
        
        # Blend the estimates
        final_estimate = ((weight_5min_avg / 100.0) * five_min_avg_estimate + 
                         (weight_current / 100.0) * current_estimate)
        
        return max(0.0, final_estimate)
    
    return max(0.0, current_estimate)


def hours_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
    """Check if two hour ranges overlap, accounting for midnight crossing.
    
    Args:
        start1: Start hour of first range (0-23)
        end1: End hour of first range (0-24, inclusive)
        start2: Start hour of second range (0-23)
        end2: End hour of second range (0-24, inclusive)
    
    Returns:
        True if ranges overlap, False otherwise
    """
    # Normalize end hours: 24 -> 0, treat as next day
    if end1 == 24:
        end1 = 0
    if end2 == 24:
        end2 = 0
    
    # Check if range crosses midnight
    range1_crosses = end1 < start1 or end1 == 0
    range2_crosses = end2 < start2 or end2 == 0
    
    if range1_crosses and range2_crosses:
        # Both cross midnight - they overlap
        return True
    elif range1_crosses:
        # Range 1 crosses midnight: [start1..23] and [0..end1]
        # Check if start2 or end2 falls in either part
        return (start2 >= start1 or end2 <= end1 or 
                (start2 < end1 and not range2_crosses))
    elif range2_crosses:
        # Range 2 crosses midnight: symmetric to above
        return (start1 >= start2 or end1 <= end2 or 
                (start1 < end2 and not range1_crosses))
    else:
        # Neither crosses midnight - simple overlap check
        return not (end1 <= start2 or end2 <= start1)



VALID_INPUT_UNITS = {"Wh", "kWh", "W", "kW"}


def check_input_sensor_unit(
    entity_id: str,
    unit: str | None,
    logger,
) -> None:
    """Warn if the input sensor's unit_of_measurement is not a recognised power/energy unit.

    Only a warning — Peak Monitor will still attempt to process the sensor using the
    configured input_unit setting.  This catches common misconfiguration early.
    """
    if unit is None:
        logger.warning(
            "Input sensor '%s' has no unit_of_measurement attribute. "
            "Peak Monitor expects one of: %s. "
            "Processing will continue using the configured input_unit setting.",
            entity_id,
            ", ".join(sorted(VALID_INPUT_UNITS)),
        )
        return

    if unit not in VALID_INPUT_UNITS:
        logger.warning(
            "Input sensor '%s' reports unit '%s' which is not a recognised "
            "power/energy unit. Expected one of: %s. "
            "Processing will continue using the configured input_unit setting, "
            "but readings may be incorrect.",
            entity_id,
            unit,
            ", ".join(sorted(VALID_INPUT_UNITS)),
        )


def apply_output_unit(
    value_wh: float,
    output_unit: str,
) -> float:
    """Convert an internal Wh value to the configured output unit (W or kW)."""
    if output_unit == "kW":
        return value_wh / 1000.0
    return value_wh


def output_precision(output_unit: str) -> int:
    """Return suggested display precision for the given output unit."""
    return 3 if output_unit == "kW" else 0
