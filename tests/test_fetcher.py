"""Tests for the meal HTML parser using the real stw-thueringen.de structure."""

import pytest
from datetime import date
from bot.fetcher import parse_meals

# Mirrors the actual stw-thueringen.de splGroupWrapper / rowMeal structure.
SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="de">
<head><title>Mensa Speiseplan</title></head>
<body>
<div class="container-fluid px-xl-0 splGroupWrapper">
    <div class="row mb-1">
        <div class="col-md-6">
            <div class="splGroup pl-3 py-2">Mittagessen</div>
        </div>
        <div class="col-md-6">
            <div class="splGroup pr-3 py-2 hide">Preise student | bedienstet | gast</div>
        </div>
        <div class="col-sm-12 d-md-none">
            <div class="splGroup">
                <div class="pl-2">Mittagessen</div>
            </div>
        </div>
    </div>
    <div class="row px-3 mb-2 rowMeal">
        <div class="container">
            <div class="row rowMealInner p-3 rounded">
                <div class="col-12 col-md-8">
                    <div class="meal-proddat hide">2024-06-17</div>
                    <div class="mealText">Pasta mit Tomatensauce</div>
                    <div class="allergene">Allergene: Wz</div>
                </div>
                <div class="col-12 col-md-4 text-right">
                    <div class="mealPreiskopf">Studierende* / Bedienstete* / G&auml;ste</div>
                    <div class="mealPreise">2,00 / 4,40 / 5,80 &euro;</div>
                </div>
            </div>
        </div>
    </div>
    <div class="row px-3 mb-2 rowMeal">
        <div class="container">
            <div class="row rowMealInner p-3 rounded">
                <div class="col-12 col-md-8">
                    <div class="meal-proddat hide">2024-06-17</div>
                    <div class="mealText">Schnitzel mit Pommes</div>
                    <div class="allergene">Allergene: Wz,Mi,Ei</div>
                </div>
                <div class="col-12 col-md-4 text-right">
                    <div class="mealPreiskopf">Studierende* / Bedienstete* / G&auml;ste</div>
                    <div class="mealPreise">4,50 / 6,70 / 8,10 &euro;</div>
                </div>
            </div>
        </div>
    </div>
</div>
<div class="container-fluid px-xl-0 splGroupWrapper">
    <div class="row mb-1">
        <div class="col-md-6">
            <div class="splGroup pl-3 py-2">Zwischenversorgung</div>
        </div>
    </div>
    <div class="row px-3 mb-2 rowMeal">
        <div class="container">
            <div class="row rowMealInner p-3 rounded">
                <div class="col-12 col-md-8">
                    <div class="meal-proddat hide">2024-06-17</div>
                    <div class="mealText">Milchreis mit Apfelmus</div>
                </div>
                <div class="col-12 col-md-4 text-right">
                    <div class="mealPreise">2,20 / 4,60 / 6,00 &euro;</div>
                </div>
            </div>
        </div>
    </div>
</div>
<div class="container-fluid px-xl-0 splGroupWrapper">
    <div class="row mb-1">
        <div class="col-md-6">
            <div class="splGroup pl-3 py-2">Abendessen</div>
        </div>
    </div>
    <div class="row px-3 mb-2 rowMeal">
        <div class="container">
            <div class="row rowMealInner p-3 rounded">
                <div class="col-12 col-md-8">
                    <div class="meal-proddat hide">2024-06-17</div>
                    <div class="mealText">Gem&#252;sesuppe mit Brot</div>
                </div>
                <div class="col-12 col-md-4 text-right">
                    <div class="mealPreise">2,50 / 4,80 / 6,20 &euro;</div>
                </div>
            </div>
        </div>
    </div>
</div>
</body>
</html>
"""

# XHR response has no meal-proddat (date already filtered server-side).
SAMPLE_XHR_HTML = """
<div class="container-fluid px-xl-0 splGroupWrapper">
    <div class="row mb-1">
        <div class="col-md-6">
            <div class="splGroup pl-3 py-2">Mittagessen</div>
        </div>
    </div>
    <div class="row px-3 mb-2 rowMeal">
        <div class="container">
            <div class="row rowMealInner p-3 rounded">
                <div class="col-12 col-md-8">
                    <div class="mealText">Karibisches Bohnen-Gem&#252;seragout</div>
                    <div class="allergene">Allergene: So</div>
                </div>
                <div class="col-12 col-md-4 text-right">
                    <div class="mealPreise">2,00 / 4,40 / 5,80 &euro;</div>
                </div>
            </div>
        </div>
    </div>
</div>
"""

EMPTY_HTML = "<html><body><p>Kein Speiseplan verf&#252;gbar.</p></body></html>"


def test_parse_finds_meals():
    meals = parse_meals(SAMPLE_HTML, date(2024, 6, 17))
    assert len(meals) >= 2


def test_parse_meal_names():
    meals = parse_meals(SAMPLE_HTML, date(2024, 6, 17))
    names = [m["name"] for m in meals]
    assert any("Pasta" in n for n in names), f"Expected 'Pasta' in names, got: {names}"


def test_parse_student_prices():
    meals = parse_meals(SAMPLE_HTML, date(2024, 6, 17))
    pasta = next((m for m in meals if "Pasta" in m.get("name", "")), None)
    assert pasta is not None
    assert pasta["price_stud"] == "2.00"


def test_parse_employee_prices():
    meals = parse_meals(SAMPLE_HTML, date(2024, 6, 17))
    pasta = next((m for m in meals if "Pasta" in m.get("name", "")), None)
    assert pasta is not None
    assert pasta["price_bed"] == "4.40"


def test_parse_categories():
    meals = parse_meals(SAMPLE_HTML, date(2024, 6, 17))
    categories = {m["category"] for m in meals}
    assert "Mittagessen" in categories
    assert "Zwischenversorgung" in categories
    assert "Abendessen" in categories


def test_parse_allergens():
    meals = parse_meals(SAMPLE_HTML, date(2024, 6, 17))
    pasta = next((m for m in meals if "Pasta" in m.get("name", "")), None)
    assert pasta is not None
    assert pasta["allergens"] == "Wz"


def test_parse_empty_html_returns_empty():
    meals = parse_meals(EMPTY_HTML, date(2024, 6, 17))
    assert isinstance(meals, list)
    assert len(meals) == 0


def test_parse_malformed_html_does_not_raise():
    bad_html = "<html><body><div unclosed"
    meals = parse_meals(bad_html, date(2024, 6, 17))
    assert isinstance(meals, list)


def test_parse_wrong_date_returns_empty():
    # Date filter: 2099 won't match any meal-proddat 2024-06-17.
    meals = parse_meals(SAMPLE_HTML, date(2099, 1, 1))
    assert isinstance(meals, list)
    assert len(meals) == 0


def test_parse_xhr_response_no_date_filter():
    # XHR responses have no meal-proddat; parse without date filter.
    meals = parse_meals(SAMPLE_XHR_HTML)
    assert len(meals) == 1
    assert "Karibisches" in meals[0]["name"]
    assert meals[0]["category"] == "Mittagessen"
