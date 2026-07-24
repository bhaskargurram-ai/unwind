"""Durable, cross-server, expiry-aware undo log (``PROJECT.md`` §7, §9, W3).

The 2026-07-28 spec RC removed protocol-level sessions, so Unwind **must** keep
its own durable log — it cannot lean on transport state (golden rule #9). This
store is a local SQLite database that survives process restart, spans all
upstream servers, and is expiry-aware (the reversibility half-life).

DECISION: implemented on the stdlib ``sqlite3`` module rather than ``aiosqlite``.
The undo log is a single-writer, local, sub-millisecond store; a synchronous
implementation is simpler and correct, and callable from both the async proxy
and the sync CLI without event-loop gymnastics. ``aiosqlite`` remains a
dependency for a future high-concurrency HTTP deployment. A test pins this
behaviour (durability across reopen).
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from unwind.types import ReversibilityClass, UndoEntry, UndoStatus, now_ts

DEFAULT_DB_PATH = Path.home() / ".unwind" / "undo.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS undo_entries (
    id          TEXT PRIMARY KEY,
    ts          REAL NOT NULL,
    server      TEXT NOT NULL,
    tool        TEXT NOT NULL,
    rev_class   INTEGER NOT NULL,
    expires_at  REAL,
    status      TEXT NOT NULL,
    session_id  TEXT,
    payload     TEXT NOT NULL          -- full UndoEntry JSON
);
CREATE INDEX IF NOT EXISTS idx_undo_ts       ON undo_entries(ts);
CREATE INDEX IF NOT EXISTS idx_undo_status   ON undo_entries(status);
CREATE INDEX IF NOT EXISTS idx_undo_session  ON undo_entries(session_id);
"""


class UndoLog:
    """A durable append-only-ish log of agent actions and their compensation plans."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(_SCHEMA)

    # -- writes -----------------------------------------------------------
    def append(self, entry: UndoEntry) -> UndoEntry:
        """Persist a new action. Returns the stored entry."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO undo_entries "
                "(id, ts, server, tool, rev_class, expires_at, status, session_id, payload) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    entry.id,
                    entry.ts,
                    entry.server,
                    entry.tool,
                    int(entry.rev_class),
                    entry.expires_at,
                    entry.status.value,
                    entry.session_id,
                    entry.model_dump_json(),
                ),
            )
        return entry

    def mark(self, entry_id: str, status: UndoStatus) -> None:
        """Update the lifecycle status of one entry."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM undo_entries WHERE id=?", (entry_id,)
            ).fetchone()
            if row is None:
                raise KeyError(entry_id)
            entry = UndoEntry.model_validate_json(row["payload"])
            entry.status = status
            self._conn.execute(
                "UPDATE undo_entries SET status=?, payload=? WHERE id=?",
                (status.value, entry.model_dump_json(), entry_id),
            )

    def expire_due(self, at: float | None = None) -> int:
        """Mark ACTIVE entries whose half-life has elapsed as EXPIRED. Returns count."""
        at = at if at is not None else now_ts()
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, payload FROM undo_entries "
                "WHERE status=? AND expires_at IS NOT NULL AND expires_at <= ?",
                (UndoStatus.ACTIVE.value, at),
            ).fetchall()
            for row in rows:
                entry = UndoEntry.model_validate_json(row["payload"])
                entry.status = UndoStatus.EXPIRED
                self._conn.execute(
                    "UPDATE undo_entries SET status=?, payload=? WHERE id=?",
                    (UndoStatus.EXPIRED.value, entry.model_dump_json(), row["id"]),
                )
            return len(rows)

    # -- reads ------------------------------------------------------------
    def get(self, entry_id: str) -> UndoEntry | None:
        row = self._conn.execute(
            "SELECT payload FROM undo_entries WHERE id=?", (entry_id,)
        ).fetchone()
        return UndoEntry.model_validate_json(row["payload"]) if row else None

    def recent(
        self,
        n: int = 20,
        *,
        session_id: str | None = None,
        status: UndoStatus | None = None,
    ) -> list[UndoEntry]:
        """Most-recent-first entries, optionally filtered by session/status."""
        clauses: list[str] = []
        params: list[object] = []
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        if status is not None:
            clauses.append("status=?")
            params.append(status.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(n)
        rows = self._conn.execute(
            f"SELECT payload FROM undo_entries {where} ORDER BY ts DESC LIMIT ?",
            params,
        ).fetchall()
        return [UndoEntry.model_validate_json(r["payload"]) for r in rows]

    def undoable(self, session_id: str | None = None) -> list[UndoEntry]:
        """ACTIVE, non-expired entries in reverse chronological order (undo stack)."""
        now = now_ts()
        return [
            e
            for e in self.recent(1000, session_id=session_id, status=UndoStatus.ACTIVE)
            if not e.is_expired(now)
        ]

    def all(self) -> Iterable[UndoEntry]:
        rows = self._conn.execute("SELECT payload FROM undo_entries ORDER BY ts DESC").fetchall()
        return [UndoEntry.model_validate_json(r["payload"]) for r in rows]

    def stats(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS c FROM undo_entries GROUP BY status"
        ).fetchall()
        out = {r["status"]: r["c"] for r in rows}
        by_class = self._conn.execute(
            "SELECT rev_class, COUNT(*) AS c FROM undo_entries GROUP BY rev_class"
        ).fetchall()
        for r in by_class:
            out[f"R{r['rev_class']}"] = r["c"]
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> UndoLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = ["DEFAULT_DB_PATH", "ReversibilityClass", "UndoLog"]
