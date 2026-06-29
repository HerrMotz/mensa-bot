"""Vote state manager.

Handles vote lifecycle: creation, ballot collection, auto-close, IRV evaluation.
Persists all state to SQLite so the bot can recover after restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from itertools import permutations
from typing import Callable, Coroutine, Optional

from .approval import evaluate_approval, ApprovalResult
from .borda import evaluate_borda, BordaResult
from .database import Database
from .irv import evaluate_irv, IRVResult
from .formatter import (
    format_approval_result,
    format_approval_ballot_accepted,
    format_approval_ballot_updated,
    format_borda_result,
    format_vote_result,
    format_ballot_accepted,
    format_ballot_updated,
    format_no_active_vote,
    format_vote_closed,
    format_invalid_ranking,
    format_invalid_approval,
)

log = logging.getLogger(__name__)


class VoteManager:
    def __init__(
        self,
        db: Database,
        mensas: list[str],
        max_poll_mensas: int,
        vote_duration_minutes: int,
        room_id: str,
        send_message: Callable[[str, str], Coroutine],
    ) -> None:
        self._db = db
        self._mensas = mensas
        self._max_poll_mensas = max_poll_mensas
        self._duration = timedelta(minutes=vote_duration_minutes)
        self._room_id = room_id
        self._send_message = send_message
        self._close_task: Optional[asyncio.Task] = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Resume any interrupted active vote on bot startup."""
        active = self._db.get_active_vote(self._room_id)
        if active:
            log.info("Unterbrochene Abstimmung (ID=%d) wird fortgesetzt.", active["id"])
            closes_at = datetime.fromisoformat(active["closes_at"])
            await self._schedule_auto_close(active["id"], closes_at)

    def has_active_vote(self) -> bool:
        return self._db.get_active_vote(self._room_id) is not None

    def get_active_vote(self) -> Optional[dict]:
        return self._db.get_active_vote(self._room_id)

    def get_poll_mode(self, voting_method: str = "borda") -> str:
        """Return 'native' or 'command' based on Mensa count and voting method.

        Approval voting lists each mensa once (no permutation explosion), so it
        can use native mode for up to 20 mensas (Matrix poll limit).
        Ranking methods (Borda/IRV) use permutations, capped at max_poll_mensas.
        """
        if voting_method == "approval":
            # Element's poll UI does not support multi-select (max_selections > 1),
            # so approval voting always uses the command-based flow.
            return "command"
        return "native" if len(self._mensas) <= self._max_poll_mensas else "command"

    def get_permutations(self) -> list[list[str]]:
        """Return all ranking permutations for native poll mode."""
        return [list(p) for p in permutations(self._mensas)]

    async def create_vote(
        self, voting_method: str = "approval"
    ) -> tuple[int, str, list[list[str]], datetime]:
        """Create a new vote session.

        Returns (session_id, poll_mode, options, closes_at).
        voting_method must be 'borda', 'irv', or 'approval'.
        """
        now = datetime.now(timezone.utc)
        closes_at = now + self._duration
        poll_mode = self.get_poll_mode(voting_method)
        if poll_mode == "native":
            if voting_method == "approval":
                options = [[m] for m in self._mensas]
            else:
                options = self.get_permutations()
        else:
            options = []

        session_id = self._db.create_vote_session(
            room_id=self._room_id,
            started_at=now.isoformat(),
            closes_at=closes_at.isoformat(),
            poll_mode=poll_mode,
            voting_method=voting_method,
        )
        if options:
            self._db.save_vote_options(session_id, options)

        await self._schedule_auto_close(session_id, closes_at)
        log.info(
            "Abstimmung gestartet (ID=%d, Modus=%s, Methode=%s, schließt: %s)",
            session_id, poll_mode, voting_method, closes_at,
        )
        return session_id, poll_mode, options, closes_at

    def set_poll_event_id(self, session_id: int, event_id: str) -> None:
        self._db.update_poll_event_id(session_id, event_id)

    async def record_native_ballot(
        self,
        session_id: int,
        user_id: str,
        display_name: Optional[str],
        option_index: int,
    ) -> Optional[str]:
        """Record a ranking ballot from a native Matrix poll (Borda/IRV).

        Returns a confirmation message or None if the session is not active.
        """
        session = self._db.get_vote_session(session_id)
        if not session or session["status"] != "open":
            return None

        options = self._db.get_vote_options(session_id)
        if option_index < 0 or option_index >= len(options):
            log.warning("Ungültiger option_index %d für Sitzung %d", option_index, session_id)
            return None

        ranking = json.loads(options[option_index]["ranking_json"])
        existing = [b for b in self._db.get_ballots(session_id) if b["user_id"] == user_id]
        is_update = bool(existing)

        self._db.upsert_ballot(
            session_id=session_id,
            user_id=user_id,
            display_name=display_name,
            option_index=option_index,
            ranking_json=json.dumps(ranking, ensure_ascii=False),
        )

        label = display_name or user_id
        if is_update:
            return format_ballot_updated(label, ranking)
        return format_ballot_accepted(label, ranking)

    async def record_approval_native_ballot(
        self,
        session_id: int,
        user_id: str,
        display_name: Optional[str],
        approved_indices: list[int],
    ) -> Optional[str]:
        """Record an approval ballot from a native Matrix poll (Approval voting).

        approved_indices: list of selected option indices (each maps to one mensa).
        Returns a confirmation message or None if the session is not active.
        """
        session = self._db.get_vote_session(session_id)
        if not session or session["status"] != "open":
            return None

        options = self._db.get_vote_options(session_id)
        approved: list[str] = []
        for idx in approved_indices:
            if 0 <= idx < len(options):
                mensa_list = json.loads(options[idx]["ranking_json"])
                if mensa_list:
                    approved.append(mensa_list[0])
            else:
                log.warning("Ungültiger option_index %d für Sitzung %d", idx, session_id)

        if not approved:
            log.warning("Leere Zustimmungsliste für %s in Sitzung %d", user_id, session_id)
            return None

        existing = [b for b in self._db.get_ballots(session_id) if b["user_id"] == user_id]
        is_update = bool(existing)

        self._db.upsert_ballot(
            session_id=session_id,
            user_id=user_id,
            display_name=display_name,
            option_index=approved_indices[0] if len(approved_indices) == 1 else None,
            ranking_json=json.dumps(approved, ensure_ascii=False),
        )

        label = display_name or user_id
        if is_update:
            return format_approval_ballot_updated(label, approved)
        return format_approval_ballot_accepted(label, approved)

    async def record_command_ballot(
        self,
        session_id: int,
        user_id: str,
        display_name: Optional[str],
        ranking_indices: list[int],
    ) -> str:
        """Record a ballot submitted via !mensa wahl command.

        For ranking methods (Borda/IRV): ranking_indices are 1-based, must be a
        full permutation of all mensas.
        For approval: ranking_indices are 1-based mensa numbers to approve (any
        non-empty subset).
        Returns a response message.
        """
        session = self._db.get_vote_session(session_id)
        if not session or session["status"] != "open":
            return format_no_active_vote()

        n = len(self._mensas)
        voting_method = session.get("voting_method", "borda")

        if voting_method == "approval":
            valid_range = set(range(1, n + 1))
            if not ranking_indices or not all(i in valid_range for i in ranking_indices):
                return format_invalid_approval(n)
            approved = [self._mensas[i - 1] for i in dict.fromkeys(ranking_indices)]
            existing = [b for b in self._db.get_ballots(session_id) if b["user_id"] == user_id]
            is_update = bool(existing)
            self._db.upsert_ballot(
                session_id=session_id,
                user_id=user_id,
                display_name=display_name,
                option_index=None,
                ranking_json=json.dumps(approved, ensure_ascii=False),
            )
            label = display_name or user_id
            if is_update:
                return format_approval_ballot_updated(label, approved)
            return format_approval_ballot_accepted(label, approved)

        # Ranking methods (Borda / IRV): require a complete permutation.
        valid = set(range(1, n + 1))
        if set(ranking_indices) != valid or len(ranking_indices) != n:
            return format_invalid_ranking(n)

        ranking = [self._mensas[i - 1] for i in ranking_indices]
        existing = [b for b in self._db.get_ballots(session_id) if b["user_id"] == user_id]
        is_update = bool(existing)

        self._db.upsert_ballot(
            session_id=session_id,
            user_id=user_id,
            display_name=display_name,
            option_index=None,
            ranking_json=json.dumps(ranking, ensure_ascii=False),
        )

        label = display_name or user_id
        if is_update:
            return format_ballot_updated(label, ranking)
        return format_ballot_accepted(label, ranking)

    async def close_vote(self, session_id: int) -> str:
        """Evaluate and close a vote. Returns the result message."""
        if self._close_task and not self._close_task.done():
            self._close_task.cancel()

        session = self._db.get_vote_session(session_id)
        if not session or session["status"] != "open":
            return format_no_active_vote()

        ballots_raw = self._db.get_ballots(session_id)

        if not ballots_raw:
            self._db.close_vote_session(session_id, winner="(keine Stimmen)", result_json="{}")
            return "Die Abstimmung wurde geschlossen. **Es wurden keine Stimmen abgegeben.**"

        # Reconstruct ranked ballots.
        ballot_list: list[list[str]] = []
        names_map: list[tuple[str, list[str]]] = []
        for b in ballots_raw:
            ranking = json.loads(b["ranking_json"])
            ballot_list.append(ranking)
            label = b.get("display_name") or b["user_id"]
            names_map.append((label, ranking))

        voting_method = session.get("voting_method", "borda")
        result = _evaluate(ballot_list, self._mensas, voting_method)
        result_json = _result_to_json(result)

        self._db.close_vote_session(session_id, winner=result.winner, result_json=result_json)

        closes_at = datetime.fromisoformat(session["closes_at"])
        return _format_result(result, names_map, session, closes_at, is_final=True)

    async def get_current_result_message(self) -> str:
        """Return a formatted result message for the currently active vote."""
        active = self._db.get_active_vote(self._room_id)
        if not active:
            return format_no_active_vote()

        ballots_raw = self._db.get_ballots(active["id"])
        ballot_list = [json.loads(b["ranking_json"]) for b in ballots_raw]
        names_map = [(b.get("display_name") or b["user_id"], json.loads(b["ranking_json"])) for b in ballots_raw]

        closes_at = datetime.fromisoformat(active["closes_at"])

        if not ballot_list:
            return (
                "🗳 **Laufende Abstimmung**\n"
                f"Endet um: {closes_at.astimezone().strftime('%H:%M Uhr')}\n\n"
                "_Noch keine Stimmen abgegeben._"
            )

        voting_method = active.get("voting_method", "borda")
        result = _evaluate(ballot_list, self._mensas, voting_method)
        return _format_result(result, names_map, active, closes_at, is_final=False)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _schedule_auto_close(self, session_id: int, closes_at: datetime) -> None:
        if self._close_task and not self._close_task.done():
            self._close_task.cancel()
        delay = (closes_at - datetime.now(timezone.utc)).total_seconds()
        if delay < 0:
            delay = 0
        self._close_task = asyncio.create_task(self._auto_close(session_id, delay))

    async def _auto_close(self, session_id: int, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            session = self._db.get_vote_session(session_id)
            if session and session["status"] == "open":
                log.info("Automatisches Schließen der Abstimmung %d.", session_id)
                message = await self.close_vote(session_id)
                await self._send_message(self._room_id, message)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("Fehler beim automatischen Schließen der Abstimmung: %s", exc)


def _evaluate(
    ballot_list: list[list[str]],
    candidates: list[str],
    voting_method: str,
) -> "ApprovalResult | BordaResult | IRVResult":
    if voting_method == "approval":
        return evaluate_approval(ballot_list, candidates)

    if len(ballot_list) == 1:
        # Single voter — first choice wins regardless of ranking method.
        winner = ballot_list[0][0] if ballot_list[0] else candidates[0]
        if voting_method == "borda":
            n = len(candidates)
            scores = {c: 0 for c in candidates}
            for pos, c in enumerate(ballot_list[0]):
                if c in scores:
                    scores[c] = n - 1 - pos
            return BordaResult(winner=winner, scores=scores, ballots=ballot_list)
        else:
            from .irv import IRVRound, IRVResult
            counts = {m: (1 if m == winner else 0) for m in candidates}
            return IRVResult(
                winner=winner,
                rounds=[IRVRound(round_number=1, counts=counts, eliminated=None)],
                ballots=ballot_list,
            )
    if voting_method == "borda":
        return evaluate_borda(ballot_list, candidates)
    return evaluate_irv(ballot_list, candidates)


def _result_to_json(result: "ApprovalResult | BordaResult | IRVResult") -> str:
    if isinstance(result, ApprovalResult):
        return json.dumps({
            "method": "approval",
            "winner": result.winner,
            "approval_counts": result.approval_counts,
            "tie_break_used": result.tie_break_used,
            "tie_break_reason": result.tie_break_reason,
        }, ensure_ascii=False)
    if isinstance(result, BordaResult):
        return json.dumps({
            "method": "borda",
            "winner": result.winner,
            "scores": result.scores,
            "tie_break_used": result.tie_break_used,
            "tie_break_reason": result.tie_break_reason,
        }, ensure_ascii=False)
    return json.dumps({
        "method": "irv",
        "winner": result.winner,
        "tie_break_used": result.tie_break_used,
        "tie_break_reason": result.tie_break_reason,
        "rounds": [
            {"round": r.round_number, "counts": r.counts, "eliminated": r.eliminated}
            for r in result.rounds
        ],
    }, ensure_ascii=False)


def _format_result(
    result: "ApprovalResult | BordaResult | IRVResult",
    names_map: list[tuple[str, list[str]]],
    session: dict,
    closes_at: "datetime",
    is_final: bool,
) -> str:
    if isinstance(result, ApprovalResult):
        return format_approval_result(
            result=result,
            ballots_with_names=names_map,
            session=session,
            closes_at=closes_at,
            is_final=is_final,
        )
    if isinstance(result, BordaResult):
        return format_borda_result(
            result=result,
            ballots_with_names=names_map,
            session=session,
            closes_at=closes_at,
            is_final=is_final,
        )
    return format_vote_result(
        result=result,
        ballots_with_names=names_map,
        session=session,
        closes_at=closes_at,
        is_final=is_final,
    )
