"""Test internal estimation algorithm."""
from datetime import datetime, timedelta

from custom_components.peak_monitor.utils import calculate_internal_estimation


class TestInternalEstimation:
    """Test internal estimation algorithm."""
    
    def test_steady_consumption_early_hour(self):
        """Test with steady 3000W consumption rate at 5 minutes into hour."""
        # 3000W for 5 minutes = 250 Wh so far
        # Should estimate 3000W * 60min = 3000 Wh for full hour
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
        
        # Should estimate ~3000 Wh
        assert 2800 <= result <= 3200, f"Expected ~3000 Wh, got {result} Wh"
    
    def test_steady_consumption_mid_hour(self):
        """Test with steady 3000W consumption at 30 minutes into hour."""
        # 3000W for 30 minutes = 1500 Wh so far
        current_time = datetime(2024, 1, 1, 10, 30, 0)
        samples = [
            (datetime(2024, 1, 1, 10, 20, 0), 1000),
            (datetime(2024, 1, 1, 10, 25, 0), 1250),
            (datetime(2024, 1, 1, 10, 30, 0), 1500),
        ]
        
        result = calculate_internal_estimation(samples, current_time)
        
        # Should estimate ~3000 Wh
        assert 2800 <= result <= 3200, f"Expected ~3000 Wh, got {result} Wh"
    
    def test_steady_consumption_late_hour(self):
        """Test with steady 3000W consumption at 55 minutes into hour."""
        # 3000W for 55 minutes = 2750 Wh so far
        current_time = datetime(2024, 1, 1, 10, 55, 0)
        samples = [
            (datetime(2024, 1, 1, 10, 45, 0), 2250),
            (datetime(2024, 1, 1, 10, 50, 0), 2500),
            (datetime(2024, 1, 1, 10, 55, 0), 2750),
        ]
        
        result = calculate_internal_estimation(samples, current_time)
        
        # Should estimate ~3000 Wh
        assert 2800 <= result <= 3200, f"Expected ~3000 Wh, got {result} Wh"
    
    def test_low_consumption_steady(self):
        """Test with low steady 500W consumption."""
        # 500W = 8.33 Wh/min
        current_time = datetime(2024, 1, 1, 10, 30, 0)
        samples = [
            (datetime(2024, 1, 1, 10, 20, 0), 166),   # 20 min * 8.33
            (datetime(2024, 1, 1, 10, 25, 0), 208),   # 25 min * 8.33
            (datetime(2024, 1, 1, 10, 30, 0), 250),   # 30 min * 8.33
        ]
        
        result = calculate_internal_estimation(samples, current_time)
        
        # Should estimate ~500 Wh
        assert 450 <= result <= 550, f"Expected ~500 Wh, got {result} Wh"
    
    def test_high_consumption_steady(self):
        """Test with high steady 10000W consumption."""
        # 10000W = 166.67 Wh/min
        current_time = datetime(2024, 1, 1, 10, 15, 0)
        samples = [
            (datetime(2024, 1, 1, 10, 5, 0), 833),     # 5 min * 166.67
            (datetime(2024, 1, 1, 10, 10, 0), 1667),   # 10 min * 166.67
            (datetime(2024, 1, 1, 10, 15, 0), 2500),   # 15 min * 166.67
        ]
        
        result = calculate_internal_estimation(samples, current_time)
        
        # Should estimate ~10000 Wh
        assert 9500 <= result <= 10500, f"Expected ~10000 Wh, got {result} Wh"
    
    def test_increasing_consumption(self):
        """Test with increasing consumption rate."""
        # Starting at 2000W, increasing to 4000W
        current_time = datetime(2024, 1, 1, 10, 30, 0)
        samples = [
            (datetime(2024, 1, 1, 10, 20, 0), 550),   # Lower rate early
            (datetime(2024, 1, 1, 10, 25, 0), 900),   # Increasing
            (datetime(2024, 1, 1, 10, 30, 0), 1400),  # Higher rate now (100 Wh in 5 min = 1200W)
        ]
        
        result = calculate_internal_estimation(samples, current_time)
        
        # Should favor recent higher rate, but not wildly overestimate
        # Recent 5 min: 500 Wh in 5 min = 6000W -> 6000 Wh/hour
        # But should be smoothed down a bit
        assert 2000 <= result <= 7000, f"Got {result} Wh"
    
    def test_no_samples(self):
        """Test with no samples."""
        current_time = datetime(2024, 1, 1, 10, 30, 0)
        samples = []
        
        result = calculate_internal_estimation(samples, current_time)
        assert result == 0.0
    
    def test_one_sample_only(self):
        """Test with only one sample - uses simple projection."""
        current_time = datetime(2024, 1, 1, 10, 30, 0)
        samples = [(datetime(2024, 1, 1, 10, 30, 0), 1500)]
        
        result = calculate_internal_estimation(samples, current_time)
        # With one sample at 30 minutes showing 1500 Wh consumed
        # Simple projection: (1500 / 30) * 60 = 3000 Wh for full hour
        assert result == 3000.0
    
    def test_two_minutes_in(self):
        """Test very early in hour - 2 minutes."""
        # This was the problem case - was giving way too low values
        current_time = datetime(2024, 1, 1, 10, 2, 0)
        samples = [
            (datetime(2024, 1, 1, 10, 0, 0), 0),
            (datetime(2024, 1, 1, 10, 1, 0), 50),    # 3000W rate
            (datetime(2024, 1, 1, 10, 2, 0), 100),   # Still 3000W rate
        ]
        
        result = calculate_internal_estimation(samples, current_time)
        
        # Should still estimate ~3000 Wh, not drop to 2 Wh!
        assert 2500 <= result <= 3500, f"Expected ~3000 Wh, got {result} Wh"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
