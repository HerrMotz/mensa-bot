"""Mensa meal fetcher.

Fetching strategy:
1. Fetch the mensa page to extract its `resources_id` (hiddenmensarscid).
2. POST to /xhr/loadspeiseplan.html with that ID and the target date.
3. Parse the XHR response using known CSS classes.

If the XHR call fails, fall back to parsing the full page HTML with date
filtering via div.meal-proddat. Empty list on any parse error.

Investigated alternatives:
- OpenMensa Thüringen parsers: unmaintained, endpoints return empty arrays.
- my-mensa.de: no JSON API.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=20)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MensaBot/1.0; "
        "+https://github.com/your-org/mensa-element-bot)"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
}

_PRICE_LINE_RE = re.compile(r"([\d,]+)\s*/\s*([\d,]+)(?:\s*/\s*([\d,]+))?\s*€")


async def fetch_html(url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """GET a URL and return the response body. Returns None on any error."""
    try:
        async with session.get(url, headers=_HEADERS, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                log.warning("HTTP %d beim Abrufen von %s", resp.status, url)
                return None
            return await resp.text(encoding="utf-8", errors="replace")
    except aiohttp.ClientError as exc:
        log.error("Netzwerkfehler beim Abrufen von %s: %s", url, exc)
        return None
    except Exception as exc:
        log.error("Unerwarteter Fehler beim Abrufen von %s: %s", url, exc)
        return None


async def fetch_meals_html(
    url: str, target_date: date, session: aiohttp.ClientSession
) -> Optional[str]:
    """Fetch the XHR meal-plan fragment for *url* on *target_date*.

    Returns the XHR response HTML (already filtered to that date), or the
    full page HTML as fallback.  Returns None when the page cannot be reached.
    """
    full_html = await fetch_html(url, session)
    if full_html is None:
        return None

    soup = BeautifulSoup(full_html, "lxml")
    id_el = soup.find("input", {"id": "hiddenmensarscid"})
    resources_id: Optional[str] = id_el.get("value") if id_el else None  # type: ignore[union-attr]

    if not resources_id:
        log.warning("Keine resources_id in %s — verwende Hauptseite.", url)
        return full_html

    parsed = urlparse(url)
    xhr_url = f"{parsed.scheme}://{parsed.netloc}/xhr/loadspeiseplan.html"
    date_de = target_date.strftime("%d.%m.%Y")

    try:
        async with session.post(
            xhr_url,
            data={"resources_id": resources_id, "date": date_de},
            headers={**_HEADERS, "X-Requested-With": "XMLHttpRequest"},
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                log.warning("XHR HTTP %d für %s am %s", resp.status, url, date_de)
                return full_html
            return await resp.text(encoding="utf-8", errors="replace")
    except Exception as exc:
        log.error("XHR-Fehler für %s: %s", url, exc)
        return full_html


def parse_meals(html: str, target_date: Optional[date] = None) -> list[dict]:
    """Parse meal plan HTML (XHR fragment or full page).

    *target_date* is used to filter meals when parsing the full page HTML
    (which may contain multiple days). XHR responses are already date-filtered
    so the argument is not needed there.

    Returns a list of dicts with keys: category, name, price_stud, price_bed, allergens.
    Returns [] on any error.
    """
    try:
        return _parse(html, target_date)
    except Exception as exc:
        log.error("Fehler beim Parsen des Speiseplans: %s", exc)
        return []


# ── Internal helpers ─────────────────────────────────────────────────────────

_DIRECT_CATEGORIES = {
    "mittagessen": "Mittagessen",
    "zwischenversorgung": "Zwischenversorgung",
    "abendessen": "Abendessen",
}

_CATEGORY_KEYWORDS = {
    "Mittagessen": ["mittag", "lunch", "hauptgericht"],
    "Zwischenversorgung": ["zwischen", "snack", "kaffeebar"],
    "Abendessen": ["abend", "dinner"],
}


def _detect_category(text: str) -> Optional[str]:
    low = text.strip().lower()
    # Exact name first.
    if low in _DIRECT_CATEGORIES:
        return _DIRECT_CATEGORIES[low]
    # Keyword fallback.
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in low for kw in keywords):
            return cat
    return None


def _parse(html: str, target_date: Optional[date]) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    date_str = target_date.strftime("%Y-%m-%d") if target_date else None
    meals: list[dict] = []

    for group in soup.find_all("div", class_="splGroupWrapper"):
        category = _group_category(group)

        for row in group.find_all("div", class_="rowMeal"):
            # Date filter: only needed when parsing full-page HTML.
            if date_str:
                proddat = row.find("div", class_="meal-proddat")
                if proddat:
                    row_date = proddat.get_text(strip=True)
                    if row_date and row_date != date_str:
                        continue

            name_el = row.find("div", class_="mealText")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            price_stud = price_bed = None
            price_el = row.find("div", class_="mealPreise")
            if price_el:
                m = _PRICE_LINE_RE.search(price_el.get_text(" ", strip=True))
                if m:
                    price_stud = m.group(1).replace(",", ".")
                    price_bed = m.group(2).replace(",", ".") if m.group(2) else None

            allergens = None
            allergen_el = row.find("div", class_="allergene")
            if allergen_el:
                raw = allergen_el.get_text(strip=True)
                if ":" in raw:
                    allergens = raw.split(":", 1)[1].strip()

            meals.append({
                "category": category,
                "name": name,
                "price_stud": price_stud,
                "price_bed": price_bed,
                "allergens": allergens,
            })

    return meals


def _group_category(group: Tag) -> str:
    """Extract the category name from a splGroupWrapper.

    The site uses two heading class names:
    - splGroup         → Mittagessen / Zwischenversorgung
    - splGroupAbendmensa → Abendessen
    """
    for class_name in ("splGroup", "splGroupAbendmensa"):
        for el in group.find_all("div", class_=class_name):
            classes = el.get("class", [])
            if "pl-3" in classes and "hide" not in classes:
                raw = el.get_text(strip=True)
                cat = _detect_category(raw)
                if cat:
                    return cat
    # Fallback: any visible heading with a recognisable category name.
    for class_name in ("splGroup", "splGroupAbendmensa"):
        for el in group.find_all("div", class_=class_name):
            if "hide" not in el.get("class", []):
                raw = el.get_text(strip=True)
                cat = _detect_category(raw)
                if cat:
                    return cat
    return "Mittagessen"
