"""Borda count evaluator.

Each voter ranks all candidates. For N candidates the top-ranked earns N-1
points, second place earns N-2, …, last place earns 0. Candidates missing
from a ballot are treated as tied last and receive 0 points from that voter.

Tie-breaking order (mirrors IRV convention):
  1. Higher total ranking score (lower average position across all ballots).
  2. Configured Mensa order (lower index wins).
A tie-break explanation is always included in the result when used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class BordaResult:
    winner: str
    scores: dict[str, int]       # candidate → total Borda points
    ballots: list[list[str]]     # original ranked ballots
    tie_break_used: bool = False
    tie_break_reason: str = ""


def evaluate_borda(
    ballots: list[list[str]],
    candidates: list[str],
) -> BordaResult:
    """Run Borda count on a list of ranked ballots.

    Each ballot is a list of candidate names in preference order (most
    preferred first).  Missing candidates receive 0 points for that ballot.
    """
    if not ballots:
        raise ValueError("Keine Stimmen vorhanden.")
    if not candidates:
        raise ValueError("Keine Kandidaten vorhanden.")

    n = len(candidates)
    scores: dict[str, int] = {c: 0 for c in candidates}

    for ballot in ballots:
        for pos, candidate in enumerate(ballot):
            if candidate in scores:
                scores[candidate] += (n - 1 - pos)

    max_score = max(scores.values())
    leaders = [c for c, s in scores.items() if s == max_score]

    tie_break_used = False
    tie_break_reason = ""

    if len(leaders) == 1:
        winner = leaders[0]
    else:
        winner, tie_break_reason = _break_tie(leaders, ballots, candidates)
        tie_break_used = True

    return BordaResult(
        winner=winner,
        scores=scores,
        ballots=ballots,
        tie_break_used=tie_break_used,
        tie_break_reason=tie_break_reason,
    )


def _break_tie(
    tied: list[str],
    ballots: list[list[str]],
    candidates: list[str],
) -> tuple[str, str]:
    # Tie-break 1: lower average position (= higher preference overall).
    avg_pos: dict[str, float] = {}
    for c in tied:
        positions = []
        for ballot in ballots:
            if c in ballot:
                positions.append(ballot.index(c))
            else:
                positions.append(len(candidates))
        avg_pos[c] = sum(positions) / len(positions)

    best_avg = min(avg_pos.values())
    still_tied = [c for c in tied if avg_pos[c] == best_avg]

    if len(still_tied) == 1:
        return still_tied[0], (
            f"Gleichstand aufgelöst durch besseren Durchschnittsrang "
            f"(Gewinner: {still_tied[0]})"
        )

    # Tie-break 2: configured order.
    winner = min(still_tied, key=lambda c: candidates.index(c))
    return winner, (
        f"Gleichstand aufgelöst nach konfigurierter Mensa-Reihenfolge "
        f"(Gewinner: {winner})"
    )
