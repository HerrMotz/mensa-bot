"""Tests for the IRV evaluator."""

import pytest
from bot.irv import evaluate_irv, IRVResult


CANDIDATES = ["Philosophenweg", "Universitätshauptgebäude", "Ernst-Abbe-Platz"]
P, U, E = CANDIDATES


def test_simple_majority():
    ballots = [
        [P, U, E],
        [P, E, U],
        [P, U, E],
    ]
    result = evaluate_irv(ballots, CANDIDATES)
    assert result.winner == P
    assert len(result.rounds) == 1


def test_irv_elimination_round():
    # E has fewest first-choice votes → eliminated; P wins.
    ballots = [
        [P, U, E],
        [P, U, E],
        [U, P, E],
        [E, P, U],
    ]
    result = evaluate_irv(ballots, CANDIDATES)
    # After E is eliminated, its ballot transfers to P → P 3, U 1 → P wins.
    assert result.winner == P


def test_full_irv_round_by_round():
    # Round 1: P=2, U=2, E=1 → E eliminated
    # Round 2: P=2, U=3 (E's ballot → U) → U wins
    ballots = [
        [P, U, E],
        [P, U, E],
        [U, P, E],
        [U, E, P],
        [E, U, P],
    ]
    result = evaluate_irv(ballots, CANDIDATES)
    assert result.winner == U
    assert len(result.rounds) >= 2


def test_single_voter():
    ballots = [[U, P, E]]
    result = evaluate_irv(ballots, CANDIDATES)
    assert result.winner == U


def test_all_equal_first_round():
    # Three candidates, each gets 1 vote first-choice.
    ballots = [
        [P, U, E],
        [U, E, P],
        [E, P, U],
    ]
    # Any tie-break path should produce a deterministic winner.
    result = evaluate_irv(ballots, CANDIDATES)
    assert result.winner in CANDIDATES


def test_tie_break_is_documented():
    ballots = [
        [P, U, E],
        [U, E, P],
        [E, P, U],
    ]
    result = evaluate_irv(ballots, CANDIDATES)
    # Tie-break used if any elimination round triggered it.
    if result.tie_break_used:
        assert result.tie_break_reason


def test_empty_ballots_raises():
    with pytest.raises(ValueError):
        evaluate_irv([], CANDIDATES)


def test_empty_candidates_raises():
    with pytest.raises(ValueError):
        evaluate_irv([[P]], [])


def test_partial_ballots():
    # Ballots that don't rank all candidates.
    ballots = [
        [P],
        [U, P],
        [E],
    ]
    result = evaluate_irv(ballots, CANDIDATES)
    assert result.winner in CANDIDATES


def test_result_has_all_rounds():
    ballots = [
        [P, U, E],
        [P, U, E],
        [U, P, E],
        [E, P, U],
    ]
    result = evaluate_irv(ballots, CANDIDATES)
    round_numbers = [r.round_number for r in result.rounds]
    assert round_numbers == list(range(1, len(round_numbers) + 1))


def test_two_candidates():
    two = ["A", "B"]
    ballots = [[two[0], two[1]], [two[1], two[0]], [two[0], two[1]]]
    result = evaluate_irv(ballots, two)
    assert result.winner == two[0]
