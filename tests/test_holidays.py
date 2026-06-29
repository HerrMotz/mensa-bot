"""Tests for Thuringian holiday and workday detection."""

from datetime import date
import pytest

from bot.holidays import thuringia_holidays, is_workday, _easter


# ── Easter calculation ────────────────────────────────────────────────────────

def test_easter_2024():
    assert _easter(2024) == date(2024, 3, 31)


def test_easter_2025():
    assert _easter(2025) == date(2025, 4, 20)


def test_easter_2026():
    assert _easter(2026) == date(2026, 4, 5)


# ── Holiday set ───────────────────────────────────────────────────────────────

def test_neujahr():
    assert date(2025, 1, 1) in thuringia_holidays(2025)


def test_karfreitag_2025():
    # Easter 2025 = Apr 20 → Good Friday = Apr 18
    assert date(2025, 4, 18) in thuringia_holidays(2025)


def test_ostermontag_2025():
    # Easter 2025 = Apr 20 → Easter Monday = Apr 21
    assert date(2025, 4, 21) in thuringia_holidays(2025)


def test_tag_der_arbeit():
    assert date(2025, 5, 1) in thuringia_holidays(2025)


def test_christi_himmelfahrt_2025():
    # Easter + 39 days = May 29
    assert date(2025, 5, 29) in thuringia_holidays(2025)


def test_pfingstmontag_2025():
    # Easter + 50 days = June 9
    assert date(2025, 6, 9) in thuringia_holidays(2025)


def test_weltkindertag_since_2019():
    assert date(2025, 9, 20) in thuringia_holidays(2025)
    assert date(2019, 9, 20) in thuringia_holidays(2019)


def test_weltkindertag_before_2019():
    assert date(2018, 9, 20) not in thuringia_holidays(2018)


def test_tag_der_deutschen_einheit():
    assert date(2025, 10, 3) in thuringia_holidays(2025)


def test_reformationstag():
    assert date(2025, 10, 31) in thuringia_holidays(2025)


def test_weihnachten():
    assert date(2025, 12, 25) in thuringia_holidays(2025)
    assert date(2025, 12, 26) in thuringia_holidays(2025)


def test_count_holidays_2025():
    # 2025: 11 holidays (Weltkindertag included)
    assert len(thuringia_holidays(2025)) == 11


# ── is_workday ────────────────────────────────────────────────────────────────

def test_monday_is_workday():
    # 2025-06-02 is a Monday and not a holiday.
    assert is_workday(date(2025, 6, 2)) is True


def test_saturday_is_not_workday():
    assert is_workday(date(2025, 6, 7)) is False


def test_sunday_is_not_workday():
    assert is_workday(date(2025, 6, 8)) is False


def test_holiday_is_not_workday():
    # Tag der deutschen Einheit 2025 falls on a Friday.
    assert is_workday(date(2025, 10, 3)) is False


def test_day_after_holiday_is_workday():
    # Oct 4 2025 is a Saturday, so test Oct 6 (Monday).
    assert is_workday(date(2025, 10, 6)) is True


def test_karfreitag_not_workday():
    assert is_workday(date(2025, 4, 18)) is False


def test_normal_friday_is_workday():
    # 2025-06-06 is a normal Friday.
    assert is_workday(date(2025, 6, 6)) is True
