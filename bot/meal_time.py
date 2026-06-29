"""Meal-time period selector.

Determines which meal category to show based on current local time.

Logic:
  Before lunch_start             → show Mittagessen (today or next available)
  lunch_start .. lunch_end       → show Mittagessen
  lunch_end .. zwischenversorgung_end → show Zwischenversorgung
  zwischenversorgung_end .. abendessen_end → show Abendessen
  After abendessen_end           → show next day's Mittagessen
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


CATEGORY_MITTAGESSEN = "Mittagessen"
CATEGORY_ZWISCHENVERSORGUNG = "Zwischenversorgung"
CATEGORY_ABENDESSEN = "Abendessen"


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def get_relevant_category(
    now: datetime | None = None,
    *,
    timezone: str = "Europe/Berlin",
    lunch_start: str = "11:00",
    lunch_end: str = "14:30",
    zwischenversorgung_start: str = "14:30",
    zwischenversorgung_end: str = "17:00",
    abendessen_start: str = "17:00",
    abendessen_end: str = "21:00",
) -> tuple[str, bool]:
    """Return (category_name, show_next_day).

    show_next_day is True when the time is past abendessen_end and we should
    show the next working day's Mittagessen.
    """
    tz = ZoneInfo(timezone)
    if now is None:
        now = datetime.now(tz)
    else:
        now = now.astimezone(tz)

    t = now.time()

    t_lunch_start = _parse_time(lunch_start)
    t_lunch_end = _parse_time(lunch_end)
    t_zw_end = _parse_time(zwischenversorgung_end)
    t_ab_end = _parse_time(abendessen_end)

    if t < t_lunch_end:
        # Before or during lunch.
        return CATEGORY_MITTAGESSEN, False
    elif t < t_zw_end:
        return CATEGORY_ZWISCHENVERSORGUNG, False
    elif t < t_ab_end:
        return CATEGORY_ABENDESSEN, False
    else:
        # After dinner — show tomorrow's lunch.
        return CATEGORY_MITTAGESSEN, True


def filter_meals_by_category(
    meals: list[dict], category: str
) -> list[dict]:
    """Return meals matching the given category (case-insensitive prefix match)."""
    cat_lower = category.lower()
    return [m for m in meals if m.get("category", "").lower().startswith(cat_lower)]
