"""Swedish holiday calculations for Peak Monitor integration."""
from datetime import datetime, timedelta


def is_swedish_holiday(date: datetime, exclude_list: list[str]) -> bool:
    """Check if the given date is a Swedish public holiday that should be excluded.
    
    Args:
        date: The date to check
        exclude_list: List of holiday identifiers to check against
        
    Returns:
        True if the date is one of the specified holidays to exclude
    """
    month = date.month
    day = date.day
    year = date.year
    weekday = date.isoweekday()
    
    # Fixed holidays
    if "new_years_day" in exclude_list and month == 1 and day == 1:
        return True
    
    if "epiphany" in exclude_list and month == 1 and day == 6:
        return True
    
    if "may_day" in exclude_list and month == 5 and day == 1:
        return True
    
    if "national_day" in exclude_list and month == 6 and day == 6:
        return True
    
    if "christmas_day" in exclude_list and month == 12 and day == 25:
        return True
    
    if "boxing_day" in exclude_list and month == 12 and day == 26:
        return True
    
    # Midsummer (Saturday between June 20-26)
    if "midsummer_day" in exclude_list:
        if _is_midsummer(month, day, weekday):
            return True
    
    # All Saints' Day (Saturday between Oct 31 - Nov 6)
    if "all_saints_day" in exclude_list:
        if _is_all_saints_day(date):
            return True
    
    # Easter-based holidays
    easter = calculate_easter(year)
    
    if "good_friday" in exclude_list:
        good_friday = easter - timedelta(days=2)
        if date.date() == good_friday.date():
            return True
    
    if "easter_sunday" in exclude_list:
        if date.date() == easter.date():
            return True
    
    if "easter_monday" in exclude_list:
        easter_monday = easter + timedelta(days=1)
        if date.date() == easter_monday.date():
            return True
    
    if "ascension_day" in exclude_list:
        ascension = easter + timedelta(days=39)
        if date.date() == ascension.date():
            return True
    
    if "whit_sunday" in exclude_list:
        whit_sunday = easter + timedelta(days=49)
        if date.date() == whit_sunday.date():
            return True
    
    return False


def _is_midsummer(month: int, day: int, weekday: int) -> bool:
    """Check if date is Midsummer (Saturday between June 20-26)."""
    return month == 6 and 20 <= day <= 26 and weekday == 6


def _is_all_saints_day(date: datetime) -> bool:
    """Check if date is All Saints' Day (Saturday between Oct 31 - Nov 6)."""
    month = date.month
    day = date.day
    weekday = date.isoweekday()
    year = date.year
    
    # Check if it's Oct 31 and a Saturday
    if month == 10 and day == 31 and weekday == 6:
        return True
    
    # Check if it's first Saturday in November
    if month == 11 and day <= 6:
        nov_1 = datetime(year, 11, 1)
        days_until_saturday = (5 - nov_1.weekday()) % 7
        all_saints = nov_1 + timedelta(days=days_until_saturday)
        return date.date() == all_saints.date()
    
    return False


def calculate_easter(year: int) -> datetime:
    """Calculate Easter Sunday using Meeus/Jones/Butcher algorithm.
    
    Args:
        year: The year to calculate Easter for
        
    Returns:
        datetime object representing Easter Sunday
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    
    return datetime(year, month, day)


def is_holiday_evening(date: datetime, exclude_list: list[str]) -> bool:
    """Check if the given date is a Swedish holiday evening (eve).
    
    Holiday evenings are the day before major holidays.
    
    Args:
        date: The date to check
        exclude_list: List of holiday evening identifiers to check
        
    Returns:
        True if the date is one of the specified holiday evenings
    """
    month = date.month
    day = date.day
    year = date.year
    weekday = date.isoweekday()
    
    if "epiphany_eve" in exclude_list:
        # January 5 (day before Epiphany)
        if month == 1 and day == 5:
            return True
    
    if "christmas_eve" in exclude_list:
        # December 24 (Christmas Eve)
        if month == 12 and day == 24:
            return True
    
    if "new_years_eve" in exclude_list:
        # December 31 (New Year's Eve)
        if month == 12 and day == 31:
            return True
    
    if "easter_eve" in exclude_list:
        # Day before Easter (Easter Saturday / Easter Eve)
        easter = calculate_easter(year)
        easter_eve = easter - timedelta(days=1)
        if date.date() == easter_eve.date():
            return True
    
    if "midsummer_eve" in exclude_list:
        # Midsummer Eve (Friday between June 19-25)
        # Midsummer is Saturday June 20-26, so eve is Friday June 19-25
        if month == 6 and 19 <= day <= 25 and weekday == 5:  # Friday
            return True
    
    return False
