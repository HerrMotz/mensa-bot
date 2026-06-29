"""Approval voting evaluator.

Each voter marks every candidate they find acceptable (any non-empty subset).
The candidate with the most approvals wins.

Tie-breaking order:
  1. Configured Mensa order (lower index wins).
A tie-break explanation is always included in the result when used.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ApprovalResult:
    winner: str
    approval_counts: dict[str, int]   # candidate → number of approvals
    ballots: list[list[str]]          # each ballot is a list of approved candidate names
    tie_break_used: bool = False
    tie_break_reason: str = ""


def evaluate_approval(
    ballots: list[list[str]],
    candidates: list[str],
) -> ApprovalResult:
    """Run approval voting on a list of approval ballots.

    Each ballot is a list of candidate names the voter finds acceptable.
    Candidates not appearing in a ballot receive 0 approvals from that voter.
    """
    if not ballots:
        raise ValueError("Keine Stimmen vorhanden.")
    if not candidates:
        raise ValueError("Keine Kandidaten vorhanden.")

    counts: dict[str, int] = {c: 0 for c in candidates}
    for ballot in ballots:
        for approved in ballot:
            if approved in counts:
                counts[approved] += 1

    max_count = max(counts.values())
    leaders = [c for c, n in counts.items() if n == max_count]

    tie_break_used = False
    tie_break_reason = ""

    if len(leaders) == 1:
        winner = leaders[0]
    else:
        winner = min(leaders, key=lambda c: candidates.index(c))
        tie_break_reason = (
            f"Gleichstand aufgelöst nach konfigurierter Mensa-Reihenfolge "
            f"(Gewinner: {winner})"
        )
        tie_break_used = True

    return ApprovalResult(
        winner=winner,
        approval_counts=counts,
        ballots=ballots,
        tie_break_used=tie_break_used,
        tie_break_reason=tie_break_reason,
    )
