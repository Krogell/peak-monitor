"""Test holiday evening detection."""
from datetime import datetime

from custom_components.peak_monitor.holidays import is_holiday_evening, calculate_easter


def test_trettondagsafton():
    """Test Trettondagsafton (January 5)."""
    # Test 2024
    date = datetime(2024, 1, 5, 12, 0)
    assert is_holiday_evening(date, ["epiphany_eve"]) == True, "Should be Trettondagsafton"
    
    # Test 2025
    date = datetime(2025, 1, 5, 18, 30)
    assert is_holiday_evening(date, ["epiphany_eve"]) == True, "Should be Trettondagsafton"
    
    # Not Trettondagsafton
    date = datetime(2024, 1, 4, 12, 0)
    assert is_holiday_evening(date, ["epiphany_eve"]) == False, "Should not be Trettondagsafton"
    
    date = datetime(2024, 1, 6, 12, 0)
    assert is_holiday_evening(date, ["epiphany_eve"]) == False, "Should not be Trettondagsafton"
    
    # Not in exclude list
    date = datetime(2024, 1, 5, 12, 0)
    assert is_holiday_evening(date, ["christmas_eve"]) == False, "Should not match when not in list"
    
    print("✅ Trettondagsafton tests passed")


def test_julafton():
    """Test Julafton (December 24)."""
    # Test 2024
    date = datetime(2024, 12, 24, 10, 0)
    assert is_holiday_evening(date, ["christmas_eve"]) == True, "Should be Julafton"
    
    # Test 2025
    date = datetime(2025, 12, 24, 19, 0)
    assert is_holiday_evening(date, ["christmas_eve"]) == True, "Should be Julafton"
    
    # Not Julafton
    date = datetime(2024, 12, 23, 12, 0)
    assert is_holiday_evening(date, ["christmas_eve"]) == False, "Should not be Julafton"
    
    date = datetime(2024, 12, 25, 12, 0)
    assert is_holiday_evening(date, ["christmas_eve"]) == False, "Should not be Julafton"
    
    print("✅ Julafton tests passed")


def test_nyarsafton():
    """Test Nyårsafton (December 31)."""
    # Test 2024
    date = datetime(2024, 12, 31, 15, 0)
    assert is_holiday_evening(date, ["new_years_eve"]) == True, "Should be Nyårsafton"
    
    # Test 2025
    date = datetime(2025, 12, 31, 22, 0)
    assert is_holiday_evening(date, ["new_years_eve"]) == True, "Should be Nyårsafton"
    
    # Not Nyårsafton
    date = datetime(2024, 12, 30, 12, 0)
    assert is_holiday_evening(date, ["new_years_eve"]) == False, "Should not be Nyårsafton"
    
    date = datetime(2025, 1, 1, 12, 0)
    assert is_holiday_evening(date, ["new_years_eve"]) == False, "Should not be Nyårsafton"
    
    print("✅ Nyårsafton tests passed")


def test_paskafton():
    """Test Påskafton (Easter Saturday/Eve)."""
    # Easter 2024 is Sunday March 31, so Påskafton is Saturday March 30
    easter_2024 = calculate_easter(2024)
    print(f"Easter 2024: {easter_2024}")
    
    date = datetime(2024, 3, 30, 12, 0)  # Saturday before Easter 2024
    assert is_holiday_evening(date, ["easter_eve"]) == True, f"Should be Påskafton 2024 (March 30)"
    
    # Easter 2025 is Sunday April 20, so Påskafton is Saturday April 19
    easter_2025 = calculate_easter(2025)
    print(f"Easter 2025: {easter_2025}")
    
    date = datetime(2025, 4, 19, 18, 0)  # Saturday before Easter 2025
    assert is_holiday_evening(date, ["easter_eve"]) == True, f"Should be Påskafton 2025 (April 19)"
    
    # Not Påskafton
    date = datetime(2024, 3, 29, 12, 0)  # Friday before
    assert is_holiday_evening(date, ["easter_eve"]) == False, "Should not be Påskafton"
    
    date = datetime(2024, 3, 31, 12, 0)  # Easter Sunday itself
    assert is_holiday_evening(date, ["easter_eve"]) == False, "Should not be Påskafton"
    
    print("✅ Påskafton tests passed")


def test_midsommarafton():
    """Test Midsommarafton (Midsummer Eve - Friday between June 19-25)."""
    # Midsummer 2024 is Saturday June 22, so Eve is Friday June 21
    date = datetime(2024, 6, 21, 14, 0)  # Friday June 21, 2024
    weekday = date.isoweekday()
    print(f"2024-06-21 is weekday {weekday} (5=Friday)")
    assert weekday == 5, "June 21, 2024 should be Friday"
    assert is_holiday_evening(date, ["midsummer_eve"]) == True, "Should be Midsommarafton 2024"
    
    # Midsummer 2025 is Saturday June 21, so Eve is Friday June 20
    date = datetime(2025, 6, 20, 16, 0)  # Friday June 20, 2025
    weekday = date.isoweekday()
    print(f"2025-06-20 is weekday {weekday} (5=Friday)")
    assert weekday == 5, "June 20, 2025 should be Friday"
    assert is_holiday_evening(date, ["midsummer_eve"]) == True, "Should be Midsommarafton 2025"
    
    # Midsummer 2026 is Saturday June 20, so Eve is Friday June 19
    date = datetime(2026, 6, 19, 19, 0)  # Friday June 19, 2026
    weekday = date.isoweekday()
    print(f"2026-06-19 is weekday {weekday} (5=Friday)")
    assert weekday == 5, "June 19, 2026 should be Friday"
    assert is_holiday_evening(date, ["midsummer_eve"]) == True, "Should be Midsommarafton 2026"
    
    # Not Midsommarafton - Saturday (the day itself)
    date = datetime(2024, 6, 22, 12, 0)  # Saturday
    assert is_holiday_evening(date, ["midsummer_eve"]) == False, "Saturday should not be Eve"
    
    # Not Midsommarafton - Thursday
    date = datetime(2024, 6, 20, 12, 0)  # Thursday
    assert is_holiday_evening(date, ["midsummer_eve"]) == False, "Thursday should not be Eve"
    
    # Not Midsommarafton - wrong month
    date = datetime(2024, 7, 19, 12, 0)  # Friday in July
    assert is_holiday_evening(date, ["midsummer_eve"]) == False, "July should not match"
    
    print("✅ Midsommarafton tests passed")


def test_multiple_evenings():
    """Test with multiple evenings in exclude list."""
    # Julafton with multiple in list
    date = datetime(2024, 12, 24, 12, 0)
    assert is_holiday_evening(date, ["epiphany_eve", "christmas_eve", "new_years_eve"]) == True
    
    # Nyårsafton with multiple in list
    date = datetime(2024, 12, 31, 12, 0)
    assert is_holiday_evening(date, ["epiphany_eve", "christmas_eve", "new_years_eve"]) == True
    
    # Not a holiday evening
    date = datetime(2024, 6, 10, 12, 0)  # Random day
    assert is_holiday_evening(date, ["epiphany_eve", "christmas_eve", "new_years_eve"]) == False
    
    print("✅ Multiple evenings tests passed")


def test_empty_list():
    """Test with empty exclude list."""
    date = datetime(2024, 12, 24, 12, 0)  # Julafton
    assert is_holiday_evening(date, []) == False, "Empty list should not match"
    
    date = datetime(2024, 12, 31, 12, 0)  # Nyårsafton
    assert is_holiday_evening(date, []) == False, "Empty list should not match"
    
    print("✅ Empty list tests passed")


def test_partial_list():
    """Test with partial exclude list."""
    # Julafton in list
    date = datetime(2024, 12, 24, 12, 0)
    assert is_holiday_evening(date, ["christmas_eve"]) == True
    
    # Nyårsafton not in list
    date = datetime(2024, 12, 31, 12, 0)
    assert is_holiday_evening(date, ["christmas_eve"]) == False, "Should not match when not in list"
    
    print("✅ Partial list tests passed")


if __name__ == "__main__":
    test_trettondagsafton()
    test_julafton()
    test_nyarsafton()
    test_paskafton()
    test_midsommarafton()
    test_multiple_evenings()
    test_empty_list()
    test_partial_list()
    
    print("\n✅ ALL HOLIDAY EVENING TESTS PASSED!")
