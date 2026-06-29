"""SQLite database layer."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

log = logging.getLogger(__name__)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS mensas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    url         TEXT NOT NULL,
    short_name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS menu_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mensa_id    INTEGER NOT NULL REFERENCES mensas(id),
    date        TEXT NOT NULL,   -- YYYY-MM-DD
    fetched_at  TEXT NOT NULL,   -- ISO-8601
    raw_html    TEXT,
    UNIQUE(mensa_id, date)
);

CREATE TABLE IF NOT EXISTS meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_id    INTEGER NOT NULL REFERENCES menu_cache(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,   -- Mittagessen / Zwischenversorgung / Abendessen
    name        TEXT NOT NULL,
    price_stud  TEXT,
    price_bed   TEXT,
    allergens   TEXT,
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS room_config (
    room_id     TEXT PRIMARY KEY,
    settings    TEXT NOT NULL DEFAULT '{}'   -- JSON blob for future per-room settings
);

CREATE TABLE IF NOT EXISTS vote_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id         TEXT NOT NULL,
    started_at      TEXT NOT NULL,   -- ISO-8601 UTC
    closes_at       TEXT NOT NULL,   -- ISO-8601 UTC
    status          TEXT NOT NULL DEFAULT 'open',   -- open / closed
    closed_at       TEXT,
    winner          TEXT,
    result_json     TEXT,            -- full result JSON
    poll_event_id   TEXT,            -- Matrix event ID of the poll start event
    poll_mode       TEXT NOT NULL DEFAULT 'native',  -- native / command
    voting_method   TEXT NOT NULL DEFAULT 'borda'    -- borda / irv
);

CREATE TABLE IF NOT EXISTS vote_options (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES vote_sessions(id) ON DELETE CASCADE,
    option_index    INTEGER NOT NULL,   -- 0-based index in the poll
    ranking_json    TEXT NOT NULL,      -- JSON list of mensa names in ranked order
    UNIQUE(session_id, option_index)
);

CREATE TABLE IF NOT EXISTS vote_ballots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES vote_sessions(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    display_name    TEXT,
    option_index    INTEGER,            -- which poll option was chosen (native mode)
    ranking_json    TEXT,               -- JSON list of mensa names (command mode)
    voted_at        TEXT NOT NULL,
    UNIQUE(session_id, user_id)
);

CREATE TABLE IF NOT EXISTS matrix_poll_events (
    event_id        TEXT PRIMARY KEY,
    session_id      INTEGER NOT NULL REFERENCES vote_sessions(id),
    event_type      TEXT NOT NULL,   -- poll.start / poll.response / poll.end
    sender          TEXT,
    content_json    TEXT,
    received_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_state (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()
        log.info("Datenbank verbunden: %s", self._path)

    def _migrate(self) -> None:
        """Add columns introduced after the initial schema without losing data."""
        assert self._conn
        existing = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(vote_sessions)")
        }
        if "voting_method" not in existing:
            self._conn.execute(
                "ALTER TABLE vote_sessions ADD COLUMN voting_method TEXT NOT NULL DEFAULT 'borda'"
            )
            log.info("Migration: Spalte voting_method zu vote_sessions hinzugefügt.")

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        assert self._conn, "DB not connected"
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ── Mensas ──────────────────────────────────────────────────────────────

    def upsert_mensa(self, name: str, url: str, short_name: str) -> int:
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO mensas(name, url, short_name) VALUES(?,?,?)
                   ON CONFLICT(name) DO UPDATE SET url=excluded.url, short_name=excluded.short_name""",
                (name, url, short_name),
            )
            row = conn.execute("SELECT id FROM mensas WHERE name=?", (name,)).fetchone()
            return row["id"]

    def get_mensa_id(self, name: str) -> Optional[int]:
        assert self._conn
        row = self._conn.execute("SELECT id FROM mensas WHERE name=?", (name,)).fetchone()
        return row["id"] if row else None

    # ── Menu cache ───────────────────────────────────────────────────────────

    def get_cache(self, mensa_id: int, date: str) -> Optional[dict]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM menu_cache WHERE mensa_id=? AND date=?",
            (mensa_id, date),
        ).fetchone()
        return dict(row) if row else None

    def set_cache(self, mensa_id: int, date: str, raw_html: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO menu_cache(mensa_id, date, fetched_at, raw_html) VALUES(?,?,?,?)
                   ON CONFLICT(mensa_id, date) DO UPDATE SET fetched_at=excluded.fetched_at, raw_html=excluded.raw_html""",
                (mensa_id, date, now, raw_html),
            )
            row = conn.execute(
                "SELECT id FROM menu_cache WHERE mensa_id=? AND date=?", (mensa_id, date)
            ).fetchone()
            return row["id"]

    def save_meals(self, cache_id: int, meals: list[dict]) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM meals WHERE cache_id=?", (cache_id,))
            for i, m in enumerate(meals):
                conn.execute(
                    "INSERT INTO meals(cache_id,category,name,price_stud,price_bed,allergens,sort_order) VALUES(?,?,?,?,?,?,?)",
                    (cache_id, m["category"], m["name"], m.get("price_stud"), m.get("price_bed"), m.get("allergens"), i),
                )

    def get_meals(self, cache_id: int) -> list[dict]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM meals WHERE cache_id=? ORDER BY sort_order", (cache_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Vote sessions ─────────────────────────────────────────────────────────

    def create_vote_session(
        self,
        room_id: str,
        started_at: str,
        closes_at: str,
        poll_mode: str = "native",
        poll_event_id: Optional[str] = None,
        voting_method: str = "borda",
    ) -> int:
        with self._tx() as conn:
            cur = conn.execute(
                """INSERT INTO vote_sessions
                   (room_id, started_at, closes_at, poll_mode, poll_event_id, voting_method)
                   VALUES(?,?,?,?,?,?)""",
                (room_id, started_at, closes_at, poll_mode, poll_event_id, voting_method),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_active_vote(self, room_id: str) -> Optional[dict]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM vote_sessions WHERE room_id=? AND status='open' ORDER BY id DESC LIMIT 1",
            (room_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_vote_session(self, session_id: int) -> Optional[dict]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM vote_sessions WHERE id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def close_vote_session(self, session_id: int, winner: str, result_json: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            conn.execute(
                """UPDATE vote_sessions SET status='closed', closed_at=?, winner=?, result_json=?
                   WHERE id=?""",
                (now, winner, result_json, session_id),
            )

    def update_poll_event_id(self, session_id: int, event_id: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE vote_sessions SET poll_event_id=? WHERE id=?",
                (event_id, session_id),
            )

    # ── Vote options ──────────────────────────────────────────────────────────

    def save_vote_options(self, session_id: int, options: list[list[str]]) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM vote_options WHERE session_id=?", (session_id,))
            for i, ranking in enumerate(options):
                conn.execute(
                    "INSERT INTO vote_options(session_id, option_index, ranking_json) VALUES(?,?,?)",
                    (session_id, i, json.dumps(ranking, ensure_ascii=False)),
                )

    def get_vote_options(self, session_id: int) -> list[dict]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM vote_options WHERE session_id=? ORDER BY option_index",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Vote ballots ──────────────────────────────────────────────────────────

    def upsert_ballot(
        self,
        session_id: int,
        user_id: str,
        display_name: Optional[str],
        option_index: Optional[int],
        ranking_json: Optional[str],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO vote_ballots(session_id, user_id, display_name, option_index, ranking_json, voted_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(session_id, user_id) DO UPDATE SET
                     display_name=excluded.display_name,
                     option_index=excluded.option_index,
                     ranking_json=excluded.ranking_json,
                     voted_at=excluded.voted_at""",
                (session_id, user_id, display_name, option_index, ranking_json, now),
            )

    def get_ballots(self, session_id: int) -> list[dict]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM vote_ballots WHERE session_id=?", (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Matrix poll events ─────────────────────────────────────────────────────

    def save_poll_event(
        self,
        event_id: str,
        session_id: int,
        event_type: str,
        sender: Optional[str],
        content_json: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO matrix_poll_events(event_id, session_id, event_type, sender, content_json, received_at)
                   VALUES(?,?,?,?,?,?)""",
                (event_id, session_id, event_type, sender, content_json, now),
            )

    # ── Bot state ─────────────────────────────────────────────────────────────

    def get_state(self, key: str) -> Optional[str]:
        assert self._conn
        row = self._conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO bot_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
