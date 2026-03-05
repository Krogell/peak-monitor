"""Unit tests for Peak Monitor integration."""
from datetime import datetime, timedelta

from custom_components.peak_monitor.holidays import (
    is_swedish_holiday,
    calculate_easter,
    _is_midsummer,
    _is_all_saints_day,
)
from custom_components.peak_monitor.utils import (
    is_time_in_range,
    hours_overlap,
    get_consumption_with_reduction,
    calculate_internal_estimation,
)


class TestHolidays:
    """Test Swedish holiday calculations."""
    
    def test_is_swedish_holiday_with_empty_list(self):
        """Test that no holidays are detected with empty exclude list."""
        # New Year's Day should not be detected if not in exclude list
        assert not is_swedish_holiday(datetime(2024, 1, 1), [])
        
        # Christmas should not be detected if not in exclude list
        assert not is_swedish_holiday(datetime(2024, 12, 25), [])
    
    def test_fixed_holidays(self):
        """Test fixed Swedish holidays."""
        # New Year's Day
        assert is_swedish_holiday(datetime(2024, 1, 1), ["new_years_day"])
        
        # Epiphany
        assert is_swedish_holiday(datetime(2024, 1, 6), ["epiphany"])
        
        # Labour Day
        assert is_swedish_holiday(datetime(2024, 5, 1), ["may_day"])
        
        # National Day
        assert is_swedish_holiday(datetime(2024, 6, 6), ["national_day"])
        
        # Christmas
        assert is_swedish_holiday(datetime(2024, 12, 25), ["christmas_day"])
        assert is_swedish_holiday(datetime(2024, 12, 26), ["boxing_day"])
    
    def test_non_holidays(self):
        """Test that regular days are not holidays."""
        exclude_list = ["new_years_day", "epiphany", "may_day", "national_day", "christmas_day", "boxing_day"]
        assert not is_swedish_holiday(datetime(2024, 3, 15), exclude_list)
        assert not is_swedish_holiday(datetime(2024, 7, 10), exclude_list)
        assert not is_swedish_holiday(datetime(2024, 9, 20), exclude_list)
    
    def test_midsummer(self):
        """Test Midsummer calculation."""
        # Midsummer is Saturday between June 20-26
        # In 2024, Midsummer is June 22 (Saturday)
        assert _is_midsummer(6, 22, 6)
        assert not _is_midsummer(6, 22, 5)  # Not Saturday
        assert not _is_midsummer(6, 19, 6)  # Too early
        assert not _is_midsummer(6, 27, 6)  # Too late
    
    def test_easter_calculation(self):
        """Test Easter calculation for known years."""
        # Known Easter dates
        assert calculate_easter(2024) == datetime(2024, 3, 31)
        assert calculate_easter(2025) == datetime(2025, 4, 20)
        assert calculate_easter(2026) == datetime(2026, 4, 5)
    
    def test_easter_holidays(self):
        """Test Easter-based holidays."""
        # 2024 Easter is March 31
        exclude_list = ["good_friday", "easter_sunday", "easter_monday", "ascension_day", "whit_sunday"]
        
        # Good Friday (2 days before)
        assert is_swedish_holiday(datetime(2024, 3, 29), exclude_list)
        
        # Easter Sunday
        assert is_swedish_holiday(datetime(2024, 3, 31), exclude_list)
        
        # Easter Monday
        assert is_swedish_holiday(datetime(2024, 4, 1), exclude_list)
        
        # Ascension Day (39 days after)
        assert is_swedish_holiday(datetime(2024, 5, 9), exclude_list)
        
        # Whit Sunday (49 days after)
        assert is_swedish_holiday(datetime(2024, 5, 19), exclude_list)
    
    def test_all_saints_day(self):
        """Test All Saints' Day calculation."""
        # All Saints' Day is the Saturday between Oct 31 - Nov 6
        # In 2024, it's November 2
        assert is_swedish_holiday(datetime(2024, 11, 2), ["all_saints_day"])
        
        # Not All Saints' Day
        assert not is_swedish_holiday(datetime(2024, 11, 1), ["all_saints_day"])
        assert not is_swedish_holiday(datetime(2024, 11, 3), ["all_saints_day"])


class TestTimeUtils:
    """Test time utility functions."""
    
    def test_time_in_range_normal(self):
        """Test time range that doesn't cross midnight."""
        # Range 6-21 (normal working hours)
        assert is_time_in_range(datetime(2024, 1, 1, 10, 0), 6, 21)
        assert is_time_in_range(datetime(2024, 1, 1, 6, 0), 6, 21)
        assert is_time_in_range(datetime(2024, 1, 1, 20, 59), 6, 21)
        
        assert not is_time_in_range(datetime(2024, 1, 1, 5, 59), 6, 21)
        assert not is_time_in_range(datetime(2024, 1, 1, 21, 0), 6, 21)
        assert not is_time_in_range(datetime(2024, 1, 1, 23, 0), 6, 21)
    
    def test_time_in_range_crossing_midnight(self):
        """Test time range that crosses midnight."""
        # Range 22-6 (night hours)
        assert is_time_in_range(datetime(2024, 1, 1, 22, 0), 22, 6)
        assert is_time_in_range(datetime(2024, 1, 1, 23, 30), 22, 6)
        assert is_time_in_range(datetime(2024, 1, 1, 0, 0), 22, 6)
        assert is_time_in_range(datetime(2024, 1, 1, 5, 59), 22, 6)
        
        assert not is_time_in_range(datetime(2024, 1, 1, 6, 0), 22, 6)
        assert not is_time_in_range(datetime(2024, 1, 1, 12, 0), 22, 6)
        assert not is_time_in_range(datetime(2024, 1, 1, 21, 59), 22, 6)
    
    def test_hours_overlap_no_overlap(self):
        """Test hour ranges that don't overlap."""
        # 6-21 and 22-6 should not overlap
        assert not hours_overlap(6, 21, 22, 6)
        
        # 8-12 and 13-17 should not overlap
        assert not hours_overlap(8, 12, 13, 17)
    
    def test_hours_overlap_with_overlap(self):
        """Test hour ranges that do overlap."""
        # 6-12 and 10-15 overlap at 10-12
        assert hours_overlap(6, 12, 10, 15)
        
        # 20-2 and 1-5 overlap at 1-2
        assert hours_overlap(20, 2, 1, 5)
        
        # 22-6 and 5-10 overlap at 5-6
        assert hours_overlap(22, 6, 5, 10)
    
    def test_hours_overlap_complete_overlap(self):
        """Test hour ranges where one contains the other."""
        # 0-24 contains everything
        assert hours_overlap(0, 24, 10, 15)
        
        # 8-18 contains 10-12
        assert hours_overlap(8, 18, 10, 12)


class TestConsumptionReduction:
    """Test consumption reduction calculations."""
    
    def test_no_reduction_when_disabled(self):
        """Test that no reduction is applied when disabled."""
        consumption = 5000.0
        result = get_consumption_with_reduction(
            consumption=consumption,
            current_time=datetime(2024, 1, 1, 23, 0),
            reduced_enabled=False,
            reduced_start=22,
            reduced_end=6,
            reduced_factor=0.5,
        )
        assert result == consumption
    
    def test_reduction_in_reduced_hours(self):
        """Test that reduction is applied during reduced hours."""
        consumption = 5000.0
        reduced_factor = 0.5
        
        # At 23:00, which is in reduced hours (22-6)
        result = get_consumption_with_reduction(
            consumption=consumption,
            current_time=datetime(2024, 1, 1, 23, 0),
            reduced_enabled=True,
            reduced_start=22,
            reduced_end=6,
            reduced_factor=reduced_factor,
        )
        assert result == consumption * reduced_factor
        assert result == 2500.0
    
    def test_no_reduction_outside_reduced_hours(self):
        """Test that no reduction is applied outside reduced hours."""
        consumption = 5000.0
        
        # At 10:00, which is not in reduced hours (22-6)
        result = get_consumption_with_reduction(
            consumption=consumption,
            current_time=datetime(2024, 1, 1, 10, 0),
            reduced_enabled=True,
            reduced_start=22,
            reduced_end=6,
            reduced_factor=0.5,
        )
        assert result == consumption
    
    def test_different_reduction_factors(self):
        """Test different reduction factors."""
        consumption = 10000.0
        
        # 50% reduction
        result_50 = get_consumption_with_reduction(
            consumption, datetime(2024, 1, 1, 23, 0),
            True, 22, 6, 0.5
        )
        assert result_50 == 5000.0
        
        # 30% reduction (keep 30% of consumption)
        result_30 = get_consumption_with_reduction(
            consumption, datetime(2024, 1, 1, 23, 0),
            True, 22, 6, 0.3
        )
        assert result_30 == 3000.0
        
        # 75% reduction
        result_75 = get_consumption_with_reduction(
            consumption, datetime(2024, 1, 1, 23, 0),
            True, 22, 6, 0.75
        )
        assert result_75 == 7500.0


class TestInternalEstimation:
    """Test internal estimation calculations."""
    
    def test_basic_estimation(self):
        """Test basic estimation with simple samples."""
        # Consumption samples: steady 3000W rate
        # At 10:05, we've consumed 250 Wh (3000W * 5min / 60min)
        current_time = datetime(2024, 1, 1, 10, 5, 0)
        samples = [
            (datetime(2024, 1, 1, 10, 0, 0), 0),
            (datetime(2024, 1, 1, 10, 1, 0), 50),
            (datetime(2024, 1, 1, 10, 2, 0), 100),
            (datetime(2024, 1, 1, 10, 3, 0), 150),
            (datetime(2024, 1, 1, 10, 4, 0), 200),
            (datetime(2024, 1, 1, 10, 5, 0), 250),
        ]
        
        result = calculate_internal_estimation(samples, current_time)
        # Should estimate 3000 Wh for full hour (50 Wh/min * 60 min)
        assert 2900 <= result <= 3100  # Allow small margin
    
    def test_estimation_early_in_hour(self):
        """Test estimation very early in the hour."""
        current_time = datetime(2024, 1, 1, 10, 1, 0)
        samples = [
            (datetime(2024, 1, 1, 10, 0, 0), 0),
            (datetime(2024, 1, 1, 10, 1, 0), 100),
        ]
        
        result = calculate_internal_estimation(samples, current_time)
        # Should estimate based on rate: 100 Wh/min * 60 = 6000 Wh
        assert 5800 <= result <= 6200  # Allow margin for calculation
    
    def test_estimation_with_previous_hour_rate(self):
        """Test estimation with fallback to previous hour rate."""
        current_time = datetime(2024, 1, 1, 10, 0, 30)  # 30 seconds into hour
        samples = []  # No samples yet
        
        # Previous hour had 2400 Wh/hour rate (40 Wh/min)
        previous_hour_rate = 2400.0 / 3600.0  # Wh per second
        
        result = calculate_internal_estimation(samples, current_time, previous_hour_rate)
        # Should use previous hour's rate as estimate
        assert result > 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_midnight_crossing_boundary(self):
        """Test boundary at midnight."""
        # Just before midnight
        assert is_time_in_range(datetime(2024, 1, 1, 23, 59), 22, 6)
        
        # Exactly midnight
        assert is_time_in_range(datetime(2024, 1, 1, 0, 0), 22, 6)
        
        # Just after midnight
        assert is_time_in_range(datetime(2024, 1, 1, 0, 1), 22, 6)
    
    def test_hour_boundaries(self):
        """Test exact hour boundaries."""
        # Start hour should be included
        assert is_time_in_range(datetime(2024, 1, 1, 6, 0), 6, 21)
        
        # End hour should be excluded
        assert not is_time_in_range(datetime(2024, 1, 1, 21, 0), 6, 21)
    
    def test_same_start_and_end_hour(self):
        """Test when start and end hour are the same."""
        # This represents a 0-hour range (no time is included)
        assert not is_time_in_range(datetime(2024, 1, 1, 10, 0), 10, 10)
        assert not is_time_in_range(datetime(2024, 1, 1, 5, 0), 10, 10)

if __name__ == "__main__":
    print("Run with: python run_tests.py")
