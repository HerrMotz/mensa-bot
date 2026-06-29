"""German message formatter for the Mensa bot.

All messages are in German. Returns plain text suitable for Matrix text messages.
HTML formatting uses Matrix's subset of HTML (for m.room.message with format=org.matrix.custom.html).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from itertools import permutations
from typing import Optional

from .approval import ApprovalResult
from .borda import BordaResult
from .irv import IRVResult, IRVRound


# ── Meal display ──────────────────────────────────────────────────────────────

def format_meals_for_mensa(
    mensa_name: str,
    meals: list[dict],
    category: str,
    target_date: datetime,
) -> str:
    """Format the meal list for one Mensa as a plain-text block."""
    lines = []
    date_str = target_date.strftime("%A, %d.%m.%Y")

    lines.append(f"🍽 **{mensa_name}** – {_translate_category(category)} ({date_str})")
    lines.append("")

    if not meals:
        lines.append("_Kein Speiseplan verfügbar._")
        return "\n".join(lines)

    for m in meals:
        name = m.get("name", "Unbekanntes Gericht")
        ps = m.get("price_stud")
        pb = m.get("price_bed")

        price_parts = []
        if ps:
            price_parts.append(f"Stud.: {_fmt_price(ps)} €")
        if pb:
            price_parts.append(f"Bed.: {_fmt_price(pb)} €")

        price_str = " | ".join(price_parts) if price_parts else "Preis unbekannt"
        lines.append(f"• {name} — {price_str}")

    return "\n".join(lines)


def format_all_mensas(
    results: list[tuple[str, list[dict], str | None]],
    category: str,
    target_date: datetime,
) -> str:
    """Format meal info for multiple Mensas.

    results: list of (mensa_name, meals, error_message_or_none)
    """
    parts = []
    for mensa_name, meals, error in results:
        if error:
            parts.append(f"🍽 **{mensa_name}**\n_{error}_")
        else:
            parts.append(format_meals_for_mensa(mensa_name, meals, category, target_date))
    separator = "\n\n" + "─" * 30 + "\n\n"
    return separator.join(parts)


def _translate_category(cat: str) -> str:
    mapping = {
        "Mittagessen": "Mittagessen",
        "Zwischenversorgung": "Zwischenversorgung",
        "Abendessen": "Abendessen",
    }
    return mapping.get(cat, cat)


def _fmt_price(price: str) -> str:
    try:
        return f"{float(price):.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return price


# ── Vote formatting ───────────────────────────────────────────────────────────

def format_vote_start_message(
    mensas: list[str],
    options: list[list[str]],
    closes_at: datetime,
    poll_mode: str,
    voting_method: str = "borda",
    poll_event_id: Optional[str] = None,
) -> str:
    """Announce a new vote in the room."""
    closes_local = closes_at.astimezone()
    time_str = closes_local.strftime("%H:%M Uhr")
    if voting_method == "borda":
        method_label = "Borda-Zählung"
    elif voting_method == "irv":
        method_label = "Instant-Runoff-Voting"
    else:
        method_label = "Approval-Voting"

    lines = [
        "🗳 **Abstimmung gestartet!**",
        "",
        f"Welche Mensa besuchen wir heute? Die Abstimmung endet um **{time_str}**.",
        f"_Auswertung per {method_label}._",
        "",
    ]

    if poll_mode == "native":
        if voting_method == "approval":
            lines.append("Wähle alle Mensen aus, die du akzeptabel findest (Mehrfachauswahl möglich):")
            for i, mensa in enumerate(mensas, 1):
                lines.append(f"  {i}. {mensa}")
        else:
            lines.append("Bitte wähle deine bevorzugte Reihenfolge im Poll:")
            for i, ranking in enumerate(options, 1):
                lines.append(f"  {i}. {' > '.join(ranking)}")
    else:
        lines.append("Da mehr als drei Mensen konfiguriert sind, stimmen wir per Befehl ab.")
        lines.append("")
        lines.append("**Kandidaten:**")
        for i, mensa in enumerate(mensas, 1):
            lines.append(f"  {i}. {mensa}")
        lines.append("")
        if voting_method == "approval":
            lines.append("Gib alle akzeptablen Mensen an mit:")
            lines.append("`!mensa votieren 1,3` (Beispiel: Mensa 1 und Mensa 3 sind akzeptabel)")
        else:
            lines.append("Gib deine Präferenz ein mit:")
            lines.append("`!mensa votieren 2,1,3` (Beispiel: Mensa 2 > Mensa 1 > Mensa 3)")

    return "\n".join(lines)


def format_vote_result(
    result: IRVResult,
    ballots_with_names: list[tuple[str, list[str]]],
    session: dict,
    closes_at: datetime,
    is_final: bool,
) -> str:
    """Format the full IRV result message."""
    lines = []

    status = "geschlossen" if is_final else "offen"
    lines.append(f"📊 **Abstimmungsergebnis** (Status: {status})")
    lines.append("")

    if not is_final:
        remaining = closes_at - datetime.now(timezone.utc)
        mins = max(0, int(remaining.total_seconds() // 60))
        secs = max(0, int(remaining.total_seconds() % 60))
        lines.append(f"⏱ Verbleibende Zeit: {mins} Min {secs} Sek")
        lines.append("")

    # Winner.
    lines.append(f"🏆 **Gewinner: {result.winner}**")
    if result.tie_break_used:
        lines.append(f"_(Gleichstand aufgelöst: {result.tie_break_reason})_")
    lines.append("")

    # Voter breakdown.
    lines.append("**Stimmen der Teilnehmenden:**")
    if ballots_with_names:
        for display_name, ranking in ballots_with_names:
            lines.append(f"• {display_name}: {' > '.join(ranking)}")
    else:
        lines.append("_Noch keine Stimmen abgegeben._")
    lines.append("")

    # IRV rounds.
    lines.append("**Auswertung (Instant-Runoff-Voting):**")
    for rnd in result.rounds:
        counts_str = ", ".join(f"{m}: {c}" for m, c in sorted(rnd.counts.items()))
        line = f"  Runde {rnd.round_number}: {counts_str}"
        if rnd.eliminated:
            line += f" → eliminiert: {rnd.eliminated}"
            if rnd.tie_break_used:
                line += f" _{rnd.tie_break_reason}_"
        else:
            line += f" → **Gewinner: {result.winner}**"
        lines.append(line)

    return "\n".join(lines)


def format_borda_result(
    result: BordaResult,
    ballots_with_names: list[tuple[str, list[str]]],
    session: dict,
    closes_at: datetime,
    is_final: bool,
) -> str:
    """Format the Borda count result message."""
    lines = []
    status = "geschlossen" if is_final else "offen"
    lines.append(f"📊 **Abstimmungsergebnis (Borda)** (Status: {status})")
    lines.append("")

    if not is_final:
        remaining = closes_at - datetime.now(timezone.utc)
        mins = max(0, int(remaining.total_seconds() // 60))
        secs = max(0, int(remaining.total_seconds() % 60))
        lines.append(f"⏱ Verbleibende Zeit: {mins} Min {secs} Sek")
        lines.append("")

    lines.append(f"🏆 **Gewinner: {result.winner}**")
    if result.tie_break_used:
        lines.append(f"_(Gleichstand aufgelöst: {result.tie_break_reason})_")
    lines.append("")

    lines.append("**Punkte (Borda-Zählung):**")
    for candidate, score in sorted(result.scores.items(), key=lambda x: -x[1]):
        marker = " 🏆" if candidate == result.winner else ""
        lines.append(f"• {candidate}: {score} Punkte{marker}")
    lines.append("")

    lines.append("**Stimmen der Teilnehmenden:**")
    if ballots_with_names:
        for display_name, ranking in ballots_with_names:
            lines.append(f"• {display_name}: {' > '.join(ranking)}")
    else:
        lines.append("_Noch keine Stimmen abgegeben._")

    return "\n".join(lines)


def format_approval_result(
    result: ApprovalResult,
    ballots_with_names: list[tuple[str, list[str]]],
    session: dict,
    closes_at: datetime,
    is_final: bool,
) -> str:
    """Format the approval voting result message."""
    lines = []
    status = "geschlossen" if is_final else "offen"
    lines.append(f"📊 **Abstimmungsergebnis (Approval)** (Status: {status})")
    lines.append("")

    if not is_final:
        remaining = closes_at - datetime.now(timezone.utc)
        mins = max(0, int(remaining.total_seconds() // 60))
        secs = max(0, int(remaining.total_seconds() % 60))
        lines.append(f"⏱ Verbleibende Zeit: {mins} Min {secs} Sek")
        lines.append("")

    lines.append(f"🏆 **Gewinner: {result.winner}**")
    if result.tie_break_used:
        lines.append(f"_(Gleichstand aufgelöst: {result.tie_break_reason})_")
    lines.append("")

    lines.append("**Zustimmungen (Approval-Voting):**")
    for candidate, count in sorted(result.approval_counts.items(), key=lambda x: -x[1]):
        marker = " 🏆" if candidate == result.winner else ""
        lines.append(f"• {candidate}: {count} Zustimmung(en){marker}")
    lines.append("")

    lines.append("**Stimmen der Teilnehmenden:**")
    if ballots_with_names:
        for display_name, approved in ballots_with_names:
            lines.append(f"• {display_name}: {', '.join(approved) if approved else '(keine)'}")
    else:
        lines.append("_Noch keine Stimmen abgegeben._")

    return "\n".join(lines)


def format_no_active_vote() -> str:
    return "Es läuft keine aktive Abstimmung."


def format_vote_already_active(closes_at: datetime) -> str:
    time_str = closes_at.astimezone().strftime("%H:%M Uhr")
    return f"Es läuft bereits eine Abstimmung (endet um {time_str}). Bitte warte, bis sie abgeschlossen ist."


def format_vote_closed(winner: str) -> str:
    return f"Die Abstimmung ist beendet. Gewinner: **{winner}**"


def format_ballot_accepted(user_display: str, ranking: list[str]) -> str:
    return f"✅ Stimme von **{user_display}** gespeichert: {' > '.join(ranking)}"


def format_ballot_updated(user_display: str, ranking: list[str]) -> str:
    return f"🔄 Stimme von **{user_display}** aktualisiert: {' > '.join(ranking)}"


def format_approval_ballot_accepted(user_display: str, approved: list[str]) -> str:
    choices = ", ".join(approved) if approved else "(keine)"
    return f"✅ Zustimmung von **{user_display}** gespeichert: {choices}"


def format_approval_ballot_updated(user_display: str, approved: list[str]) -> str:
    choices = ", ".join(approved) if approved else "(keine)"
    return f"🔄 Zustimmung von **{user_display}** aktualisiert: {choices}"


def format_invalid_ranking(num_mensas: int) -> str:
    return (
        f"Ungültige Wahl. Bitte gib eine kommagetrennte Liste mit den Zahlen 1–{num_mensas} an.\n"
        f"Beispiel: `!mensa votieren 2,1,3`"
    )


def format_invalid_approval(num_mensas: int) -> str:
    return (
        f"Ungültige Wahl. Bitte gib eine kommagetrennte Liste von Mensa-Nummern (1–{num_mensas}) an.\n"
        f"Beispiel: `!mensa votieren 1,3` (bedeutet: Mensa 1 und Mensa 3 sind akzeptabel)"
    )


def format_help() -> str:
    return """**MensaBot – Verfügbare Befehle:**

`!mensa` oder `!m` – Zeigt die aktuell relevanten Speisen der konfigurierten Mensen
`!mensa mittag` – Zeigt das Mittagessen
`!mensa zwischen` – Zeigt die Zwischenversorgung
`!mensa abend` – Zeigt das Abendessen
`!mensa start` – Startet eine Abstimmung (Standard-Methode aus Konfiguration)
`!mensa start approval` – Startet eine Approval-Abstimmung (markiere alle akzeptablen Mensen)
`!mensa start borda` – Startet eine Abstimmung per Borda-Zählung
`!mensa start irv` – Startet eine Abstimmung per Instant-Runoff-Voting
`!mensa votieren 1,3` – Gibt eine Stimme ab (Bedeutung je nach Methode)
`!mensa ergebnis` – Zeigt das aktuelle Abstimmungsergebnis
`!mensa schließen` – Schließt die aktuelle Abstimmung manuell
`!mensa hilfe` – Zeigt diese Hilfemeldung

_Kurzform `!m` funktioniert für alle Befehle, z. B. `!m start`, `!m votieren 1,2`._
_Abstimmungsmethoden: Approval (Standard), Borda-Zählung, Instant-Runoff-Voting._"""


# ── Poll event content builder ────────────────────────────────────────────────

def build_approval_poll_content(
    mensas: list[str],
    duration_minutes: int,
) -> dict:
    """Build a Matrix MSC3381 poll for approval voting.

    Each mensa is a separate option; voters may select any number of them.
    """
    question_text = "Welche Mensen sind für dich akzeptabel? (Mehrfachauswahl möglich)"

    stable_options = [
        {"m.id": str(i), "m.text": mensa}
        for i, mensa in enumerate(mensas)
    ]
    unstable_options = [
        {
            "id": str(i),
            "org.matrix.msc1767.text": mensa,
            "body": mensa,
        }
        for i, mensa in enumerate(mensas)
    ]

    return {
        "m.poll": {
            "question": {"m.text": question_text},
            "kind": "m.disclosed",
            "max_selections": len(mensas),
            "answers": stable_options,
        },
        "org.matrix.msc3381.poll.start": {
            "question": {
                "org.matrix.msc1767.text": question_text,
                "body": question_text,
            },
            "kind": "org.matrix.msc3381.poll.disclosed",
            "max_selections": len(mensas),
            "answers": unstable_options,
        },
        "org.matrix.msc1767.text": question_text,
        "body": question_text,
        "msgtype": "m.text",
    }


def build_native_poll_content(
    mensas: list[str],
    options: list[list[str]],
    duration_minutes: int,
) -> dict:
    """Build the Matrix MSC3381 / m.poll.start event content.

    Uses numeric string IDs ("0", "1", ...) so the response handler can
    convert them back to option indices with int().

    Stable (Matrix 1.7+) and unstable (MSC3381) use different field names:
    - stable answers: "m.id" / "m.text"
    - unstable answers: "id" / "org.matrix.msc1767.text" (+ "body" fallback)
    Both blocks are included so Element and other clients work regardless of
    which spec version they implement.
    """
    question_text = "Welche Mensa besuchen wir heute? (Wähle deine bevorzugte Reihenfolge)"

    # Stable options (Matrix 1.7+ m.poll).
    stable_options = [
        {
            "m.id": str(i),
            "m.text": " > ".join(ranking),
        }
        for i, ranking in enumerate(options)
    ]

    # Unstable options (MSC3381 org.matrix.msc3381.poll.start).
    unstable_options = [
        {
            "id": str(i),
            "org.matrix.msc1767.text": " > ".join(ranking),
            "body": " > ".join(ranking),
        }
        for i, ranking in enumerate(options)
    ]

    return {
        # Stable spec types (Matrix 1.7+).
        "m.poll": {
            "question": {"m.text": question_text},
            "kind": "m.disclosed",
            "max_selections": 1,
            "answers": stable_options,
        },
        # Unstable MSC3381 types for Element compatibility.
        "org.matrix.msc3381.poll.start": {
            "question": {
                "org.matrix.msc1767.text": question_text,
                "body": question_text,
            },
            "kind": "org.matrix.msc3381.poll.disclosed",
            "max_selections": 1,
            "answers": unstable_options,
        },
        "org.matrix.msc1767.text": question_text,
        "body": question_text,
        "msgtype": "m.text",
    }
