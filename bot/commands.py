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
    subcommand: str           # "mensa", "heute", "mittag", "zwischen", "abend", "start", "votieren", "ergebnis", "schliessen", "hilfe"
    raw_args: str             # everything after the subcommand
    ranking_indices: Optional[list[int]] = None  # parsed from "votieren" (ballot) subcommand


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
    "start": "start",           # start a vote
    "abstimmung": "start",
    "wahl": "start",
    "votieren": "votieren",     # cast a ballot
    "ergebnis": "ergebnis",
    "result": "ergebnis",
    "schließen": "schliessen",
    "schliessen": "schliessen",
    "schluss": "schliessen",
    "beenden": "schliessen",
    "hilfe": "hilfe",
    "help": "hilfe",
}


def parse_command(
    text: str, prefixes: "str | list[str]" = "!mensa"
) -> Optional[ParsedCommand]:
    """Parse a message text. Returns None if it is not a recognised bot command.

    prefixes may be a single string or a list; the first matching prefix wins.
    """
    if isinstance(prefixes, str):
        prefixes = [prefixes]

    text = text.strip()

    used_prefix: Optional[str] = None
    for p in prefixes:
        if text.lower().startswith(p.lower()):
            used_prefix = p
            break
    if used_prefix is None:
        return None

    rest = text[len(used_prefix):].strip()
    parts = rest.split(None, 1)

    subword = parts[0].lower() if parts else ""
    raw_args = parts[1].strip() if len(parts) > 1 else ""

    subcommand = _SUBCOMMAND_ALIASES.get(subword)
    if subcommand is None:
        # Unknown subcommand — treat as "hilfe".
        log.debug("Unbekannter Unterbefehl: %r", subword)
        return ParsedCommand(subcommand="hilfe", raw_args="")

    cmd = ParsedCommand(subcommand=subcommand, raw_args=raw_args)

    if subcommand == "votieren":
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
