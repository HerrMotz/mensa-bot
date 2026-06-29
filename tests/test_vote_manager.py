"""Tests for VoteManager and persistence/restart recovery."""

import asyncio
import json
import os
import tempfile
import pytest

from bot.database import Database
from bot.vote_manager import VoteManager


MENSAS = ["Philosophenweg", "Universitätshauptgebäude", "Ernst-Abbe-Platz"]
ROOM = "!testroom:matrix.org"

_sent_messages: list[tuple[str, str]] = []


async def _fake_send(room_id: str, text: str) -> None:
    _sent_messages.append((room_id, text))


@pytest.fixture()
def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.connect()
    for m in MENSAS:
        db.upsert_mensa(m, f"https://example.com/{m}", m)
    yield db
    db.close()


@pytest.fixture()
def vm(db):
    _sent_messages.clear()
    return VoteManager(
        db=db,
        mensas=MENSAS,
        max_poll_mensas=3,
        vote_duration_minutes=20,
        room_id=ROOM,
        send_message=_fake_send,
    )


# ── Poll mode ─────────────────────────────────────────────────────────────────

def test_poll_mode_native_for_3_mensas(vm):
    assert vm.get_poll_mode("borda") == "native"


def test_poll_mode_command_for_4_mensas(db):
    mensas_4 = MENSAS + ["Carl-Zeiss-Promenade"]
    db.upsert_mensa("Carl-Zeiss-Promenade", "https://x.com", "CZP")
    vm4 = VoteManager(
        db=db, mensas=mensas_4, max_poll_mensas=3,
        vote_duration_minutes=20, room_id=ROOM, send_message=_fake_send,
    )
    assert vm4.get_poll_mode("borda") == "command"


def test_poll_mode_approval_always_command(vm, db):
    # Approval voting always uses command mode because Element polls don't
    # support multi-select (max_selections > 1).
    assert vm.get_poll_mode("approval") == "command"
    db.upsert_mensa("Carl-Zeiss-Promenade", "https://x.com", "CZP")
    mensas_4 = MENSAS + ["Carl-Zeiss-Promenade"]
    vm4 = VoteManager(
        db=db, mensas=mensas_4, max_poll_mensas=3,
        vote_duration_minutes=20, room_id=ROOM, send_message=_fake_send,
    )
    assert vm4.get_poll_mode("approval") == "command"


def test_permutations_count(vm):
    perms = vm.get_permutations()
    assert len(perms) == 6  # 3! = 6


# ── Vote lifecycle ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_vote_approval(vm):
    # Approval always uses command mode (Element polls don't support multi-select).
    session_id, poll_mode, options, closes_at = await vm.create_vote("approval")
    assert session_id > 0
    assert poll_mode == "command"
    assert options == []
    assert vm.has_active_vote()


@pytest.mark.asyncio
async def test_create_vote_borda(vm):
    session_id, poll_mode, options, closes_at = await vm.create_vote("borda")
    assert session_id > 0
    assert poll_mode == "native"
    assert len(options) == 6  # 3! permutations
    assert vm.has_active_vote()


@pytest.mark.asyncio
async def test_no_active_vote_initially(vm):
    assert not vm.has_active_vote()


@pytest.mark.asyncio
async def test_record_native_ballot(vm):
    session_id, _, options, _ = await vm.create_vote("borda")
    msg = await vm.record_native_ballot(session_id, "@anna:matrix.org", "Anna", 0)
    assert msg is not None
    assert "Anna" in msg


@pytest.mark.asyncio
async def test_update_ballot(vm):
    session_id, _, _, _ = await vm.create_vote("borda")
    await vm.record_native_ballot(session_id, "@anna:matrix.org", "Anna", 0)
    msg = await vm.record_native_ballot(session_id, "@anna:matrix.org", "Anna", 1)
    assert msg is not None
    assert "aktualisiert" in msg.lower()


@pytest.mark.asyncio
async def test_record_approval_command_ballot(vm):
    session_id, _, _, _ = await vm.create_vote("approval")
    msg = await vm.record_command_ballot(
        session_id, "@anna:matrix.org", "Anna", [1, 3]
    )
    assert msg is not None
    assert "Anna" in msg
    # Should show approved mensas joined by comma, not " > ".
    assert ">" not in msg


@pytest.mark.asyncio
async def test_command_ballot_valid_borda(vm, db):
    db.upsert_mensa("Carl-Zeiss-Promenade", "https://x.com", "CZP")
    mensas_4 = MENSAS + ["Carl-Zeiss-Promenade"]
    vm4 = VoteManager(
        db=db, mensas=mensas_4, max_poll_mensas=3,
        vote_duration_minutes=20, room_id=ROOM, send_message=_fake_send,
    )
    await vm4.create_vote("borda")
    active = vm4.get_active_vote()
    msg = await vm4.record_command_ballot(
        active["id"], "@max:matrix.org", "Max", [2, 1, 4, 3]
    )
    assert "Max" in msg


@pytest.mark.asyncio
async def test_command_ballot_valid_approval(vm, db):
    db.upsert_mensa("Carl-Zeiss-Promenade", "https://x.com", "CZP")
    mensas_4 = MENSAS + ["Carl-Zeiss-Promenade"]
    vm4 = VoteManager(
        db=db, mensas=mensas_4, max_poll_mensas=3,
        vote_duration_minutes=20, room_id=ROOM, send_message=_fake_send,
    )
    await vm4.create_vote("approval")
    active = vm4.get_active_vote()
    # Approval accepts any non-empty subset.
    msg = await vm4.record_command_ballot(
        active["id"], "@max:matrix.org", "Max", [1, 3]
    )
    assert "Max" in msg


@pytest.mark.asyncio
async def test_command_ballot_invalid_indices_borda(vm, db):
    db.upsert_mensa("Carl-Zeiss-Promenade", "https://x.com", "CZP")
    mensas_4 = MENSAS + ["Carl-Zeiss-Promenade"]
    vm4 = VoteManager(
        db=db, mensas=mensas_4, max_poll_mensas=3,
        vote_duration_minutes=20, room_id=ROOM, send_message=_fake_send,
    )
    await vm4.create_vote("borda")
    active = vm4.get_active_vote()
    msg = await vm4.record_command_ballot(
        active["id"], "@max:matrix.org", "Max", [1, 1, 1, 1]  # duplicates
    )
    assert "ungültig" in msg.lower()


@pytest.mark.asyncio
async def test_command_ballot_invalid_indices_approval(vm, db):
    db.upsert_mensa("Carl-Zeiss-Promenade", "https://x.com", "CZP")
    mensas_4 = MENSAS + ["Carl-Zeiss-Promenade"]
    vm4 = VoteManager(
        db=db, mensas=mensas_4, max_poll_mensas=3,
        vote_duration_minutes=20, room_id=ROOM, send_message=_fake_send,
    )
    await vm4.create_vote("approval")
    active = vm4.get_active_vote()
    # Index 5 is out of range for 4 mensas.
    msg = await vm4.record_command_ballot(
        active["id"], "@max:matrix.org", "Max", [1, 5]
    )
    assert "ungültig" in msg.lower()


@pytest.mark.asyncio
async def test_close_vote_with_ballots(vm):
    session_id, _, options, _ = await vm.create_vote("borda")
    await vm.record_native_ballot(session_id, "@anna:matrix.org", "Anna", 0)
    await vm.record_native_ballot(session_id, "@max:matrix.org", "Max", 1)

    msg = await vm.close_vote(session_id)
    assert "Gewinner" in msg
    assert not vm.has_active_vote()


@pytest.mark.asyncio
async def test_close_approval_vote_with_ballots(vm):
    session_id, _, _, _ = await vm.create_vote("approval")
    await vm.record_command_ballot(session_id, "@anna:matrix.org", "Anna", [1, 2])
    await vm.record_command_ballot(session_id, "@max:matrix.org", "Max", [1])

    msg = await vm.close_vote(session_id)
    assert "Gewinner" in msg
    assert not vm.has_active_vote()


@pytest.mark.asyncio
async def test_close_vote_no_ballots(vm):
    session_id, _, _, _ = await vm.create_vote("approval")
    msg = await vm.close_vote(session_id)
    assert "keine stimmen" in msg.lower()


@pytest.mark.asyncio
async def test_get_current_result_no_vote(vm):
    msg = await vm.get_current_result_message()
    assert "keine" in msg.lower()


@pytest.mark.asyncio
async def test_result_message_during_vote(vm):
    session_id, _, options, _ = await vm.create_vote("borda")
    await vm.record_native_ballot(session_id, "@anna:matrix.org", "Anna", 0)
    msg = await vm.get_current_result_message()
    assert "Anna" in msg


@pytest.mark.asyncio
async def test_result_message_during_approval_vote(vm):
    session_id, _, _, _ = await vm.create_vote("approval")
    await vm.record_command_ballot(session_id, "@anna:matrix.org", "Anna", [1, 3])
    msg = await vm.get_current_result_message()
    assert "Anna" in msg


# ── Restart recovery ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restart_recovery(tmp_path):
    """Bot restart should resume a pending vote."""
    db = Database(str(tmp_path / "recovery.db"))
    db.connect()
    for m in MENSAS:
        db.upsert_mensa(m, f"https://example.com/{m}", m)

    vm1 = VoteManager(
        db=db, mensas=MENSAS, max_poll_mensas=3,
        vote_duration_minutes=20, room_id=ROOM, send_message=_fake_send,
    )
    session_id, _, _, _ = await vm1.create_vote("approval")
    assert vm1.has_active_vote()

    # Simulate restart — new VoteManager instance, same DB.
    vm2 = VoteManager(
        db=db, mensas=MENSAS, max_poll_mensas=3,
        vote_duration_minutes=20, room_id=ROOM, send_message=_fake_send,
    )
    await vm2.start()
    assert vm2.has_active_vote()

    db.close()
