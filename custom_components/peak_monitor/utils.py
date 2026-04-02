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
    interval_minutes: int = 60,
) -> float:
    """Calculate estimated consumption for the current interval.

    Works for any interval length (6, 12, 15, 20, 30, 60, 120 min).
    Time is measured from the start of the current interval, not the clock hour.

    Formula: E_est(t) = E(t) + P_avg(t) × (interval - t) / 60

    Where:
    - E(t) = accumulated energy so far this interval (Wh)
    - P_avg(t) = mean instantaneous power over recent samples (W)
    - t = minutes elapsed since interval start
    - interval = configured interval length in minutes

    Big Drop Filter:
    - Filters out samples before a consumption drop >= 5 kW (5000 W)
    - This prevents misleading high estimates when large loads turn off

    Startup blending (first 5 min of interval): smoothly transitions from
    previous-interval rate to current samples to avoid a jarring jump.

    Args:
        consumption_samples: List of (timestamp, cumulative_consumption_this_interval) tuples
        current_time: Current datetime
        previous_hour_rate: Rate in Wh/second from previous interval (for startup blending)
        interval_minutes: Configured interval length in minutes (default 60)

    Returns:
        Estimated consumption for the full interval (Wh)
    """
    if not consumption_samples:
        # No data — project previous rate over this interval
        if previous_hour_rate is not None and previous_hour_rate > 0:
            return previous_hour_rate * (interval_minutes * 60)
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
    
    # Calculate seconds elapsed since the start of the current interval
    interval_seconds = interval_minutes * 60
    if interval_minutes >= 60:
        # Boundaries at hour multiples — position within a multi-hour window
        step_hours = interval_minutes // 60
        interval_start_hour = (current_time.hour // step_hours) * step_hours
        seconds_elapsed = (current_time.hour - interval_start_hour) * 3600 + current_time.minute * 60 + current_time.second
    else:
        # Sub-hour intervals aligned to :00 of each clock hour
        interval_start_minute = (current_time.minute // interval_minutes) * interval_minutes
        seconds_elapsed = (current_time.minute - interval_start_minute) * 60 + current_time.second
    
    # If we're at the very start of the interval, use previous rate projection
    if seconds_elapsed < 1:
        if previous_hour_rate is not None and previous_hour_rate > 0:
            return previous_hour_rate * interval_seconds
        return max(0.0, E_t)
    
    # Calculate minutes elapsed since interval start
    t = seconds_elapsed / 60.0

    # Calculate remaining minutes in this interval
    remaining_minutes = float(interval_minutes) - t

    # If we're at the end of the interval, no remaining time to estimate
    if remaining_minutes <= 0:
        return max(0.0, E_t)
    
    # Calculate current algorithm estimate
    if len(filtered_samples) < 2:
        # Only one sample - simple projection
        current_estimate = (E_t / t) * float(interval_minutes) if t > 0 else 0.0
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
            # High-load step detection: when the most recent power sample represents
            # a step increase of >= LARGE_STEP_W compared to the sample before it,
            # weight the recent samples 3× more heavily so the estimate catches up
            # quickly (e.g. EV charger plugged in mid-interval).
            # A steady high load (no step) uses the plain mean — it is already
            # correctly captured by the accumulated E(t) term.
            LARGE_STEP_W = 3500.0
            HIGH_LOAD_WEIGHT = 3.0

            large_step_detected = (
                len(powers) >= 2
                and (powers[-1] - powers[-2]) >= LARGE_STEP_W
            )

            if large_step_detected:
                # Give the last ⌈N/3⌉ samples (post-step readings) 3× weight
                recent_count = max(1, len(powers) // 3)
                older = powers[:-recent_count]
                recent = powers[-recent_count:]
                total_weight = len(older) * 1.0 + len(recent) * HIGH_LOAD_WEIGHT
                P_avg = (
                    sum(older) * 1.0 + sum(recent) * HIGH_LOAD_WEIGHT
                ) / total_weight
            else:
                # No large step — plain mean
                P_avg = sum(powers) / len(powers)

            # Apply formula: E_est(t) = E(t) + P_avg(t) × remaining_minutes / 60
            current_estimate = E_t + (P_avg * remaining_minutes / 60.0)
    
    # Startup blending: smooth transition for first 20% of the interval
    # (capped at 300 s / 5 min so very long intervals don't blend too long).
    blend_window = min(300, interval_seconds // 5)
    if seconds_elapsed < blend_window and previous_hour_rate is not None and previous_hour_rate > 0:
        # Weight for current-samples estimate rises linearly from 0→100%
        weight_current = (seconds_elapsed / blend_window) * 100.0
        weight_prev = 100.0 - weight_current

        # Previous-rate projection over this interval length
        prev_rate_estimate = previous_hour_rate * interval_seconds

        final_estimate = ((weight_prev / 100.0) * prev_rate_estimate +
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
