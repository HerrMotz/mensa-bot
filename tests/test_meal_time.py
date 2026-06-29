"""Tests for the meal-time period selector."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.meal_time import (
    CATEGORY_ABENDESSEN,
    CATEGORY_MITTAGESSEN,
    CATEGORY_ZWISCHENVERSORGUNG,
    filter_meals_by_category,
    get_relevant_category,
)

TZ = "Europe/Berlin"
_tz = ZoneInfo(TZ)


def _dt(h: int, m: int = 0) -> datetime:
    return datetime(2024, 6, 17, h, m, tzinfo=_tz)


def test_before_lunch():
    cat, next_day = get_relevant_category(now=_dt(9, 0), timezone=TZ)
    assert cat == CATEGORY_MITTAGESSEN
    assert not next_day


def test_during_lunch():
    cat, next_day = get_relevant_category(now=_dt(12, 0), timezone=TZ)
    assert cat == CATEGORY_MITTAGESSEN
    assert not next_day


def test_at_lunch_boundary():
    # Exactly at lunch_end → Zwischenversorgung starts.
    cat, next_day = get_relevant_category(now=_dt(14, 30), timezone=TZ)
    assert cat == CATEGORY_ZWISCHENVERSORGUNG
    assert not next_day


def test_zwischenversorgung():
    cat, next_day = get_relevant_category(now=_dt(15, 0), timezone=TZ)
    assert cat == CATEGORY_ZWISCHENVERSORGUNG
    assert not next_day


def test_abendessen():
    cat, next_day = get_relevant_category(now=_dt(18, 0), timezone=TZ)
    assert cat == CATEGORY_ABENDESSEN
    assert not next_day


def test_after_abendessen_shows_next_day():
    cat, next_day = get_relevant_category(now=_dt(22, 0), timezone=TZ)
    assert cat == CATEGORY_MITTAGESSEN
    assert next_day


def test_custom_times():
    cat, _ = get_relevant_category(
        now=_dt(10, 0),
        timezone=TZ,
        lunch_start="10:00",
        lunch_end="13:00",
        zwischenversorgung_start="13:00",
        zwischenversorgung_end="15:00",
        abendessen_start="15:00",
        abendessen_end="20:00",
    )
    assert cat == CATEGORY_MITTAGESSEN


def test_filter_meals_by_category():
    meals = [
        {"category": "Mittagessen", "name": "Schnitzel"},
        {"category": "Zwischenversorgung", "name": "Kuchen"},
        {"category": "Abendessen", "name": "Suppe"},
        {"category": "Mittagessen", "name": "Pasta"},
    ]
    filtered = filter_meals_by_category(meals, "Mittagessen")
    assert len(filtered) == 2
    assert all(m["category"] == "Mittagessen" for m in filtered)


def test_filter_case_insensitive():
    meals = [{"category": "mittagessen", "name": "Test"}]
    filtered = filter_meals_by_category(meals, "Mittagessen")
    assert len(filtered) == 1


def test_filter_empty():
    filtered = filter_meals_by_category([], "Mittagessen")
    assert filtered == []
