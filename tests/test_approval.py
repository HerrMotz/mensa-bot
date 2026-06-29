"""Tests for the Approval voting evaluator."""

import pytest
from bot.approval import evaluate_approval, ApprovalResult

CANDIDATES = ["Philosophenweg", "UHG", "Ernst-Abbe-Platz"]


def test_clear_winner():
    ballots = [
        ["Philosophenweg", "UHG"],
        ["Philosophenweg"],
        ["Philosophenweg", "Ernst-Abbe-Platz"],
    ]
    result = evaluate_approval(ballots, CANDIDATES)
    assert result.winner == "Philosophenweg"
    assert result.approval_counts["Philosophenweg"] == 3
    assert result.tie_break_used is False


def test_counts_are_correct():
    ballots = [
        ["Philosophenweg", "UHG"],
        ["UHG", "Ernst-Abbe-Platz"],
        ["Philosophenweg"],
    ]
    result = evaluate_approval(ballots, CANDIDATES)
    assert result.approval_counts["Philosophenweg"] == 2
    assert result.approval_counts["UHG"] == 2
    assert result.approval_counts["Ernst-Abbe-Platz"] == 1


def test_tie_break_by_configured_order():
    # Philosophenweg and UHG both have 2 approvals → first in list wins.
    ballots = [
        ["Philosophenweg", "UHG"],
        ["UHG", "Philosophenweg"],
    ]
    result = evaluate_approval(ballots, CANDIDATES)
    assert result.winner == "Philosophenweg"
    assert result.tie_break_used is True
    assert "Philosophenweg" in result.tie_break_reason


def test_single_voter():
    ballots = [["Ernst-Abbe-Platz"]]
    result = evaluate_approval(ballots, CANDIDATES)
    assert result.winner == "Ernst-Abbe-Platz"
    assert result.approval_counts["Ernst-Abbe-Platz"] == 1
    assert result.approval_counts["Philosophenweg"] == 0


def test_all_approved_by_all():
    ballots = [
        ["Philosophenweg", "UHG", "Ernst-Abbe-Platz"],
        ["Philosophenweg", "UHG", "Ernst-Abbe-Platz"],
    ]
    result = evaluate_approval(ballots, CANDIDATES)
    # All tied → first in configured order wins.
    assert result.winner == "Philosophenweg"
    assert result.tie_break_used is True


def test_candidate_not_in_any_ballot_gets_zero():
    ballots = [["Philosophenweg"], ["UHG"]]
    result = evaluate_approval(ballots, CANDIDATES)
    assert result.approval_counts["Ernst-Abbe-Platz"] == 0


def test_result_contains_all_candidates():
    ballots = [["Philosophenweg"]]
    result = evaluate_approval(ballots, CANDIDATES)
    assert set(result.approval_counts.keys()) == set(CANDIDATES)


def test_empty_ballots_raises():
    with pytest.raises(ValueError):
        evaluate_approval([], CANDIDATES)


def test_empty_candidates_raises():
    with pytest.raises(ValueError):
        evaluate_approval([["Philosophenweg"]], [])


def test_two_candidates_clear_winner():
    ballots = [
        ["Philosophenweg"],
        ["Philosophenweg"],
        ["UHG"],
    ]
    result = evaluate_approval(ballots, ["Philosophenweg", "UHG"])
    assert result.winner == "Philosophenweg"
    assert result.approval_counts["Philosophenweg"] == 2
    assert result.approval_counts["UHG"] == 1
    assert result.tie_break_used is False


def test_ballots_stored_on_result():
    ballots = [["Philosophenweg", "UHG"], ["Ernst-Abbe-Platz"]]
    result = evaluate_approval(ballots, CANDIDATES)
    assert result.ballots == ballots
