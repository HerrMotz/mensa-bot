"""Instant-runoff voting (IRV) evaluator.

Tie-breaking order (documented default):
  1. Most first-choice votes in the *original* (round-1) ballot.
  2. Best total ranking score (lower = better; each candidate scored by sum of positions).
  3. Configured Mensa order (index in the original candidates list).
  4. A tie-break explanation is always included in the result when used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IRVRound:
    round_number: int
    counts: dict[str, int]          # mensa → first-choice count
    eliminated: Optional[str]       # None for the final round
    tie_break_used: bool = False
    tie_break_reason: str = ""


@dataclass
class IRVResult:
    winner: str
    rounds: list[IRVRound]
    ballots: list[list[str]]        # original ballots (each a ranked list of mensa names)
    tie_break_used: bool = False
    tie_break_reason: str = ""


def evaluate_irv(
    ballots: list[list[str]],
    candidates: list[str],          # original ordered candidate list (for tie-break #3)
) -> IRVResult:
    """Run IRV on a list of ranked ballots.

    Each ballot is a list of candidate names in preference order (most preferred first).
    Candidates not appearing in a ballot are ignored for that ballot.
    """
    if not ballots:
        raise ValueError("Keine Stimmen vorhanden.")
    if not candidates:
        raise ValueError("Keine Kandidaten vorhanden.")

    active = list(candidates)
    rounds: list[IRVRound] = []

    # For tie-break #1: count first-choice votes in the original round.
    original_first_choice = _count_first_choices(ballots, active)

    # For tie-break #2: total ranking score over all original ballots.
    total_score = _compute_ranking_scores(ballots, candidates)

    overall_tie_break_used = False
    overall_tie_break_reason = ""

    round_num = 1
    while len(active) > 1:
        counts = _count_first_choices(ballots, active)
        total_votes = sum(counts.values())

        # Check for majority winner.
        for mensa, count in counts.items():
            if count > total_votes / 2:
                rounds.append(IRVRound(round_number=round_num, counts=counts, eliminated=None))
                return IRVResult(
                    winner=mensa,
                    rounds=rounds,
                    ballots=ballots,
                    tie_break_used=overall_tie_break_used,
                    tie_break_reason=overall_tie_break_reason,
                )

        # Find the minimum count.
        min_count = min(counts.values())
        losers = [m for m, c in counts.items() if c == min_count]

        tie_used = False
        tie_reason = ""
        if len(losers) > 1:
            # Apply tie-break to decide who gets eliminated.
            loser, tie_reason = _break_elimination_tie(
                losers, original_first_choice, total_score, candidates
            )
            tie_used = True
            overall_tie_break_used = True
            overall_tie_break_reason = tie_reason
        else:
            loser = losers[0]

        rounds.append(IRVRound(
            round_number=round_num,
            counts=counts,
            eliminated=loser,
            tie_break_used=tie_used,
            tie_break_reason=tie_reason,
        ))
        active.remove(loser)
        round_num += 1

    # One candidate remains.
    final_counts = _count_first_choices(ballots, active)
    rounds.append(IRVRound(round_number=round_num, counts=final_counts, eliminated=None))
    return IRVResult(
        winner=active[0],
        rounds=rounds,
        ballots=ballots,
        tie_break_used=overall_tie_break_used,
        tie_break_reason=overall_tie_break_reason,
    )


def _count_first_choices(ballots: list[list[str]], active: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {m: 0 for m in active}
    for ballot in ballots:
        for choice in ballot:
            if choice in counts:
                counts[choice] += 1
                break
    return counts


def _compute_ranking_scores(ballots: list[list[str]], candidates: list[str]) -> dict[str, float]:
    """Lower score = higher overall preference."""
    scores: dict[str, float] = {m: 0.0 for m in candidates}
    for ballot in ballots:
        for pos, mensa in enumerate(ballot):
            if mensa in scores:
                scores[mensa] += pos
        # Penalise candidates not ranked by a voter.
        ranked = set(ballot)
        for mensa in candidates:
            if mensa not in ranked:
                scores[mensa] += len(candidates)
    return scores


def _break_elimination_tie(
    tied: list[str],
    original_first: dict[str, int],
    total_score: dict[str, float],
    candidates: list[str],
) -> tuple[str, str]:
    """Return the candidate to eliminate and an explanation string."""
    # Among tied losers, eliminate the one with the fewest original first-choice votes.
    min_orig = min(original_first.get(m, 0) for m in tied)
    still_tied = [m for m in tied if original_first.get(m, 0) == min_orig]

    if len(still_tied) == 1:
        return still_tied[0], (
            f"Gleichstand aufgelöst durch wenigste Erststimmen in Runde 1 "
            f"(eliminiert: {still_tied[0]})"
        )

    # Apply ranking score.
    max_score = max(total_score.get(m, 0) for m in still_tied)
    still_tied2 = [m for m in still_tied if total_score.get(m, 0) == max_score]

    if len(still_tied2) == 1:
        return still_tied2[0], (
            f"Gleichstand aufgelöst durch schlechtesten Gesamt-Rangwert "
            f"(eliminiert: {still_tied2[0]})"
        )

    # Fall back to configured order — eliminate the one that appears last in candidates.
    loser = max(still_tied2, key=lambda m: candidates.index(m))
    return loser, (
        f"Gleichstand aufgelöst nach konfigurierter Mensa-Reihenfolge "
        f"(eliminiert: {loser})"
    )
