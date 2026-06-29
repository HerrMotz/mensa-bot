"""Thuringian public holiday calculator.

Covers all statutory holidays in Thuringia (Thüringen), Germany, including
Easter-based dates and the state-specific Weltkindertag (from 2019) and
Reformationstag.
"""

from __future__ import annotations

from datetime import date, timedelta


def _easter(year: int) -> date:
    """Compute Easter Sunday for the given year (Anonymous Gregorian algorithm)."""
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
    return date(year, month, day)


def thuringia_holidays(year: int) -> frozenset[date]:
    """Return the set of public holidays in Thuringia for the given year."""
    easter = _easter(year)
    holidays: set[date] = {
        date(year, 1, 1),            # Neujahrstag
        easter - timedelta(days=2),  # Karfreitag
        easter + timedelta(days=1),  # Ostermontag
        date(year, 5, 1),            # Tag der Arbeit
        easter + timedelta(days=39), # Christi Himmelfahrt
        easter + timedelta(days=50), # Pfingstmontag
        date(year, 10, 3),           # Tag der deutschen Einheit
        date(year, 10, 31),          # Reformationstag
        date(year, 12, 25),          # 1. Weihnachtstag
        date(year, 12, 26),          # 2. Weihnachtstag
    }
    if year >= 2019:
        holidays.add(date(year, 9, 20))  # Weltkindertag
    return frozenset(holidays)


def is_workday(d: date) -> bool:
    """Return True if *d* is a weekday (Mon–Fri) and not a Thuringian holiday."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return d not in thuringia_holidays(d.year)
