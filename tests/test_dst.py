"""Test timezone and DST handling for daily resets."""
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo



def calculate_next_midnight(current_time):
    """
    Calculate next midnight in local timezone.
    This mimics the _schedule_next_daily_reset logic.
    """
    next_midnight = (current_time + timedelta(days=1)).replace(
        hour=0, minute=0, second=5, microsecond=0
    )
    return next_midnight


class TestDSTHandling:
    """Test daylight saving time transitions."""
    
    def test_winter_time_february_sweden(self):
        """Test scheduling in winter (CET = UTC+1)."""
        # February 15, 2026, 15:30 CET (winter time)
        stockholm_tz = ZoneInfo("Europe/Stockholm")
        current = datetime(2026, 2, 15, 15, 30, 0, tzinfo=stockholm_tz)
        
        next_midnight = calculate_next_midnight(current)
        
        # Should be February 16, 2026 at 00:00:05 CET
        assert next_midnight.year == 2026
        assert next_midnight.month == 2
        assert next_midnight.day == 16
        assert next_midnight.hour == 0
        assert next_midnight.minute == 0
        assert next_midnight.second == 5
        
        # Check timezone is preserved
        assert next_midnight.tzinfo == stockholm_tz
        
        # In February, Sweden is UTC+1 (CET)
        utc_offset = next_midnight.utcoffset()
        assert utc_offset.total_seconds() == 3600  # 1 hour
        
        print(f"✓ Winter (Feb): {current} -> {next_midnight}")
        print(f"  UTC offset: {utc_offset} (expected: 1 hour)")
    
    def test_summer_time_june_sweden(self):
        """Test scheduling in summer (CEST = UTC+2)."""
        # June 15, 2026, 15:30 CEST (summer time)
        stockholm_tz = ZoneInfo("Europe/Stockholm")
        current = datetime(2026, 6, 15, 15, 30, 0, tzinfo=stockholm_tz)
        
        next_midnight = calculate_next_midnight(current)
        
        # Should be June 16, 2026 at 00:00:05 CEST
        assert next_midnight.year == 2026
        assert next_midnight.month == 6
        assert next_midnight.day == 16
        assert next_midnight.hour == 0
        assert next_midnight.minute == 0
        assert next_midnight.second == 5
        
        # Check timezone is preserved
        assert next_midnight.tzinfo == stockholm_tz
        
        # In June, Sweden is UTC+2 (CEST, daylight saving)
        utc_offset = next_midnight.utcoffset()
        assert utc_offset.total_seconds() == 7200  # 2 hours
        
        print(f"✓ Summer (Jun): {current} -> {next_midnight}")
        print(f"  UTC offset: {utc_offset} (expected: 2 hours)")
    
    def test_spring_forward_transition(self):
        """Test the spring DST transition (clocks move forward)."""
        # In 2026, Europe/Stockholm springs forward on March 29 at 02:00 -> 03:00
        stockholm_tz = ZoneInfo("Europe/Stockholm")
        
        # March 28, 2026, 15:00 CET (day before transition)
        before_transition = datetime(2026, 3, 28, 15, 0, 0, tzinfo=stockholm_tz)
        next_midnight = calculate_next_midnight(before_transition)
        
        # Should be March 29, 2026 at 00:00:05 CET
        # This is BEFORE the 02:00->03:00 transition
        assert next_midnight.year == 2026
        assert next_midnight.month == 3
        assert next_midnight.day == 29
        assert next_midnight.hour == 0
        
        # At midnight on March 29, still UTC+1 (transition happens at 02:00)
        utc_offset_before = next_midnight.utcoffset()
        assert utc_offset_before.total_seconds() == 3600  # Still 1 hour
        
        print(f"✓ Spring forward - before: {before_transition} -> {next_midnight}")
        print(f"  UTC offset: {utc_offset_before} (1 hour, before 02:00 transition)")
        
        # Now test scheduling FROM the transition day
        # March 29, 2026, 15:00 CEST (after transition, clocks already moved forward)
        on_transition_day = datetime(2026, 3, 29, 15, 0, 0, tzinfo=stockholm_tz)
        next_midnight_2 = calculate_next_midnight(on_transition_day)
        
        # Should be March 30, 2026 at 00:00:05 CEST
        assert next_midnight_2.year == 2026
        assert next_midnight_2.month == 3
        assert next_midnight_2.day == 30
        assert next_midnight_2.hour == 0
        
        # On March 30, it's UTC+2 (CEST)
        utc_offset_after = next_midnight_2.utcoffset()
        assert utc_offset_after.total_seconds() == 7200  # 2 hours
        
        print(f"✓ Spring forward - after: {on_transition_day} -> {next_midnight_2}")
        print(f"  UTC offset: {utc_offset_after} (2 hours, after transition)")
    
    def test_fall_back_transition(self):
        """Test the fall DST transition (clocks move back)."""
        # In 2026, Europe/Stockholm falls back on October 25 at 03:00 -> 02:00
        stockholm_tz = ZoneInfo("Europe/Stockholm")
        
        # October 24, 2026, 15:00 CEST (day before transition)
        before_transition = datetime(2026, 10, 24, 15, 0, 0, tzinfo=stockholm_tz)
        next_midnight = calculate_next_midnight(before_transition)
        
        # Should be October 25, 2026 at 00:00:05 CEST
        assert next_midnight.year == 2026
        assert next_midnight.month == 10
        assert next_midnight.day == 25
        assert next_midnight.hour == 0
        
        # At midnight on October 25, still UTC+2 (transition happens at 03:00)
        utc_offset_before = next_midnight.utcoffset()
        assert utc_offset_before.total_seconds() == 7200  # Still 2 hours
        
        print(f"✓ Fall back - before: {before_transition} -> {next_midnight}")
        print(f"  UTC offset: {utc_offset_before} (2 hours, before 03:00 transition)")
        
        # Test scheduling FROM the transition day
        # October 25, 2026, 15:00 CET (after transition, clocks moved back)
        on_transition_day = datetime(2026, 10, 25, 15, 0, 0, tzinfo=stockholm_tz)
        next_midnight_2 = calculate_next_midnight(on_transition_day)
        
        # Should be October 26, 2026 at 00:00:05 CET
        assert next_midnight_2.year == 2026
        assert next_midnight_2.month == 10
        assert next_midnight_2.day == 26
        assert next_midnight_2.hour == 0
        
        # On October 26, it's UTC+1 (CET)
        utc_offset_after = next_midnight_2.utcoffset()
        assert utc_offset_after.total_seconds() == 3600  # 1 hour
        
        print(f"✓ Fall back - after: {on_transition_day} -> {next_midnight_2}")
        print(f"  UTC offset: {utc_offset_after} (1 hour, after transition)")
    
    def test_utc_to_sweden_conversion(self):
        """Test that midnight local time is NOT midnight UTC."""
        stockholm_tz = ZoneInfo("Europe/Stockholm")
        
        # February midnight in Stockholm
        feb_midnight = datetime(2026, 2, 16, 0, 0, 5, tzinfo=stockholm_tz)
        feb_utc = feb_midnight.astimezone(ZoneInfo("UTC"))
        
        # In February (CET = UTC+1), midnight in Stockholm is 23:00 previous day UTC
        assert feb_utc.day == 15
        assert feb_utc.hour == 23
        assert feb_utc.minute == 0
        
        print(f"✓ Feb midnight local: {feb_midnight}")
        print(f"  In UTC: {feb_utc} (23:00 previous day)")
        
        # June midnight in Stockholm  
        june_midnight = datetime(2026, 6, 16, 0, 0, 5, tzinfo=stockholm_tz)
        june_utc = june_midnight.astimezone(ZoneInfo("UTC"))
        
        # In June (CEST = UTC+2), midnight in Stockholm is 22:00 previous day UTC
        assert june_utc.day == 15
        assert june_utc.hour == 22
        assert june_utc.minute == 0
        
        print(f"✓ Jun midnight local: {june_midnight}")
        print(f"  In UTC: {june_utc} (22:00 previous day)")


def run_all_tests():
    """Run all DST tests."""
    print("Testing Daylight Saving Time Handling")
    print("=" * 60)
    
    test = TestDSTHandling()
    
    try:
        print("\n1. Winter Time (February - CET)")
        print("-" * 60)
        test.test_winter_time_february_sweden()
        
        print("\n2. Summer Time (June - CEST)")
        print("-" * 60)
        test.test_summer_time_june_sweden()
        
        print("\n3. Spring Forward Transition (March)")
        print("-" * 60)
        test.test_spring_forward_transition()
        
        print("\n4. Fall Back Transition (October)")
        print("-" * 60)
        test.test_fall_back_transition()
        
        print("\n5. UTC Conversion Verification")
        print("-" * 60)
        test.test_utc_to_sweden_conversion()
        
        print("\n" + "=" * 60)
        print("✅ ALL DST TESTS PASSED!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(run_all_tests())
