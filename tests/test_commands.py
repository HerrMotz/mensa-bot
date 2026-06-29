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


def test_votieren():
    cmd = parse_command("!mensa votieren")
    assert cmd.subcommand == "votieren"


def test_abstimmung_alias():
    cmd = parse_command("!mensa abstimmung")
    assert cmd.subcommand == "votieren"


def test_wahl_with_ranking():
    cmd = parse_command("!mensa wahl 2,1,3")
    assert cmd.subcommand == "wahl"
    assert cmd.ranking_indices == [2, 1, 3]


def test_wahl_no_args():
    cmd = parse_command("!mensa wahl")
    assert cmd.subcommand == "wahl"
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


def test_different_prefix():
    cmd = parse_command("!bot mensa", prefix="!bot")
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


def test_wahl_spaces_in_ranking():
    cmd = parse_command("!mensa wahl 1, 3, 2")
    assert cmd.ranking_indices == [1, 3, 2]


def test_wahl_invalid_ranking():
    cmd = parse_command("!mensa wahl abc")
    assert cmd.ranking_indices is None
