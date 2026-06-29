"""Tests for the command parser."""

import pytest
from bot.commands import parse_command, ParsedCommand


def test_bare_command():
    cmd = parse_command("!mensa")
    assert cmd is not None
    assert cmd.subcommand == "mensa"


def test_heute():
    cmd = parse_command("!mensa heute")
    assert cmd.subcommand == "heute"


def test_start():
    cmd = parse_command("!mensa start")
    assert cmd.subcommand == "start"


def test_start_with_method():
    cmd = parse_command("!mensa start borda")
    assert cmd.subcommand == "start"
    assert cmd.raw_args == "borda"


def test_abstimmung_alias():
    cmd = parse_command("!mensa abstimmung")
    assert cmd.subcommand == "start"


def test_votieren_casts_ballot():
    cmd = parse_command("!mensa votieren 2,1,3")
    assert cmd.subcommand == "votieren"
    assert cmd.ranking_indices == [2, 1, 3]


def test_votieren_no_args():
    cmd = parse_command("!mensa votieren")
    assert cmd.subcommand == "votieren"
    assert cmd.ranking_indices is None


def test_votieren_spaces_in_indices():
    cmd = parse_command("!mensa votieren 1, 3, 2")
    assert cmd.ranking_indices == [1, 3, 2]


def test_votieren_invalid_indices():
    cmd = parse_command("!mensa votieren abc")
    assert cmd.ranking_indices is None


def test_ergebnis():
    cmd = parse_command("!mensa ergebnis")
    assert cmd.subcommand == "ergebnis"


def test_schliessen():
    cmd = parse_command("!mensa schließen")
    assert cmd.subcommand == "schliessen"


def test_schliessen_ascii_alias():
    cmd = parse_command("!mensa schliessen")
    assert cmd.subcommand == "schliessen"


def test_schluss_alias():
    cmd = parse_command("!mensa schluss")
    assert cmd.subcommand == "schliessen"


def test_wahl_alias_starts_vote():
    cmd = parse_command("!mensa wahl")
    assert cmd.subcommand == "start"


def test_short_prefix_wahl():
    cmd = parse_command("!m wahl", prefixes=["!mensa", "!m"])
    assert cmd.subcommand == "start"


def test_hilfe():
    cmd = parse_command("!mensa hilfe")
    assert cmd.subcommand == "hilfe"


def test_help_alias():
    cmd = parse_command("!mensa help")
    assert cmd.subcommand == "hilfe"


def test_unknown_subcommand_returns_hilfe():
    cmd = parse_command("!mensa unbekannt")
    assert cmd.subcommand == "hilfe"


def test_not_a_command():
    cmd = parse_command("Hallo, was gibt es heute?")
    assert cmd is None


# ── Short prefix !m ──────────────────────────────────────────────────────────

def test_short_prefix_bare():
    cmd = parse_command("!m", prefixes=["!mensa", "!m"])
    assert cmd is not None
    assert cmd.subcommand == "mensa"


def test_short_prefix_heute():
    cmd = parse_command("!m heute", prefixes=["!mensa", "!m"])
    assert cmd.subcommand == "heute"


def test_short_prefix_start():
    cmd = parse_command("!m start", prefixes=["!mensa", "!m"])
    assert cmd.subcommand == "start"


def test_short_prefix_votieren():
    cmd = parse_command("!m votieren 1,2", prefixes=["!mensa", "!m"])
    assert cmd.subcommand == "votieren"
    assert cmd.ranking_indices == [1, 2]


def test_long_prefix_still_works():
    cmd = parse_command("!mensa start borda", prefixes=["!mensa", "!m"])
    assert cmd.subcommand == "start"
    assert cmd.raw_args == "borda"


def test_short_prefix_not_recognised_without_list():
    # When only the long prefix is passed, !m should not match.
    cmd = parse_command("!m heute", prefixes="!mensa")
    assert cmd is None


# ── Other ────────────────────────────────────────────────────────────────────

def test_different_prefix():
    cmd = parse_command("!bot mensa", prefixes="!bot")
    assert cmd is not None
    assert cmd.subcommand == "mensa"


def test_case_insensitive_prefix():
    cmd = parse_command("!MENSA heute")
    assert cmd is not None
    assert cmd.subcommand == "heute"


def test_whitespace_trimmed():
    cmd = parse_command("  !mensa   heute  ")
    assert cmd is not None
    assert cmd.subcommand == "heute"
