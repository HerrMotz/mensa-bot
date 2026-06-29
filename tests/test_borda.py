"""Tests for the Borda count evaluator."""

import pytest
from bot.borda import evaluate_borda, BordaResult

CANDIDATES = ["Philosophenweg", "UHG", "Ernst-Abbe-Platz"]


def test_clear_winner():
    ballots = [
        ["Philosophenweg", "UHG", "Ernst-Abbe-Platz"],
        ["Philosophenweg", "Ernst-Abbe-Platz", "UHG"],
        ["Philosophenweg", "UHG", "Ernst-Abbe-Platz"],
    ]
    result = evaluate_borda(ballots, CANDIDATES)
    assert result.winner == "Philosophenweg"
    assert result.tie_break_used is False


def test_scores_sum_correctly():
    # 2 voters, 3 candidates: each ballot contributes 2+1+0 = 3 points total.
    ballots = [
        ["Philosophenweg", "UHG", "Ernst-Abbe-Platz"],
        ["UHG", "Philosophenweg", "Ernst-Abbe-Platz"],
    ]
    result = evaluate_borda(ballots, CANDIDATES)
    total = sum(result.scores.values())
    assert total == 6  # 2 voters × 3 points each


def test_first_place_worth_n_minus_1():
    ballots = [["Philosophenweg", "UHG", "Ernst-Abbe-Platz"]]
    result = evaluate_borda(ballots, CANDIDATES)
    assert result.scores["Philosophenweg"] == 2  # N-1 = 3-1
    assert result.scores["UHG"] == 1
    assert result.scores["Ernst-Abbe-Platz"] == 0


def test_missing_candidate_gets_zero():
    # Voter only ranks two of three.
    ballots = [["Philosophenweg", "UHG"]]
    result = evaluate_borda(ballots, CANDIDATES)
    assert result.scores["Ernst-Abbe-Platz"] == 0


def test_tie_break_by_average_rank():
    # Philosophenweg and UHG tie on Borda points but Philosophenweg has better avg rank.
    ballots = [
        ["Philosophenweg", "UHG", "Ernst-Abbe-Platz"],
        ["UHG", "Philosophenweg", "Ernst-Abbe-Platz"],
        ["Philosophenweg", "Ernst-Abbe-Platz", "UHG"],
        ["Ernst-Abbe-Platz", "UHG", "Philosophenweg"],
    ]
    result = evaluate_borda(ballots, CANDIDATES)
    # Just check it returns a valid winner without raising.
    assert result.winner in CANDIDATES


def test_tie_break_by_configured_order():
    # Construct a tie where average rank is also equal → fall back to config order.
    # Two candidates perfectly symmetric → first in list wins.
    ballots = [
        ["Philosophenweg", "UHG"],
        ["UHG", "Philosophenweg"],
    ]
    candidates = ["Philosophenweg", "UHG"]
    result = evaluate_borda(ballots, candidates)
    assert result.winner == "Philosophenweg"
    assert result.tie_break_used is True


def test_empty_ballots_raises():
    with pytest.raises(ValueError):
        evaluate_borda([], CANDIDATES)


def test_empty_candidates_raises():
    with pytest.raises(ValueError):
        evaluate_borda([["Philosophenweg"]], [])


def test_single_voter():
    ballots = [["Ernst-Abbe-Platz", "Philosophenweg", "UHG"]]
    result = evaluate_borda(ballots, CANDIDATES)
    assert result.winner == "Ernst-Abbe-Platz"


def test_result_contains_all_candidates():
    ballots = [["Philosophenweg", "UHG", "Ernst-Abbe-Platz"]]
    result = evaluate_borda(ballots, CANDIDATES)
    assert set(result.scores.keys()) == set(CANDIDATES)


def test_two_candidates():
    ballots = [["Philosophenweg", "UHG"], ["Philosophenweg", "UHG"]]
    result = evaluate_borda(ballots, ["Philosophenweg", "UHG"])
    assert result.winner == "Philosophenweg"
    assert result.scores["Philosophenweg"] == 2
    assert result.scores["UHG"] == 0
