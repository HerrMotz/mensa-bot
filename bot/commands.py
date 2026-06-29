"""Command parser and dispatcher.

Parses incoming Matrix messages starting with the configured command prefix
and routes them to the correct handler.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class ParsedCommand:
    subcommand: str           # "mensa", "heute", "mittag", "zwischen", "abend", "votieren", "wahl", "ergebnis", "schließen", "hilfe"
    raw_args: str             # everything after the subcommand
    ranking_indices: Optional[list[int]] = None  # parsed from "wahl" subcommand


_SUBCOMMAND_ALIASES: dict[str, str] = {
    "": "mensa",
    "mensa": "mensa",
    "heute": "heute",
    "mittag": "mittag",
    "mittagessen": "mittag",
    "zwischen": "zwischen",
    "zwischenversorgung": "zwischen",
    "abend": "abend",
    "abendessen": "abend",
    "votieren": "votieren",
    "abstimmung": "votieren",
    "wahl": "wahl",
    "ergebnis": "ergebnis",
    "result": "ergebnis",
    "schließen": "schliessen",
    "schliessen": "schliessen",
    "beenden": "schliessen",
    "hilfe": "hilfe",
    "help": "hilfe",
}


def parse_command(text: str, prefix: str = "!mensa") -> Optional[ParsedCommand]:
    """Parse a message text. Returns None if it's not a bot command."""
    text = text.strip()

    if not text.lower().startswith(prefix.lower()):
        return None

    rest = text[len(prefix):].strip()
    parts = rest.split(None, 1)

    subword = parts[0].lower() if parts else ""
    raw_args = parts[1].strip() if len(parts) > 1 else ""

    subcommand = _SUBCOMMAND_ALIASES.get(subword)
    if subcommand is None:
        # Unknown subcommand — treat as "hilfe".
        log.debug("Unbekannter Unterbefehl: %r", subword)
        return ParsedCommand(subcommand="hilfe", raw_args="")

    cmd = ParsedCommand(subcommand=subcommand, raw_args=raw_args)

    if subcommand == "wahl":
        cmd.ranking_indices = _parse_ranking(raw_args)

    return cmd


def _parse_ranking(raw: str) -> Optional[list[int]]:
    """Parse a comma-separated ranking like '2,1,3' into [2, 1, 3]."""
    try:
        parts = [p.strip() for p in raw.split(",")]
        indices = [int(p) for p in parts if p]
        if not indices:
            return None
        return indices
    except ValueError:
        return None
