"""Unit tests for the durable undo log (``unwind/undolog/store.py``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from unwind.types import ReversibilityClass, UndoEntry, UndoStatus
from unwind.undolog.store import UndoLog


def _entry(
    eid: str,
    *,
    session: str = "sess",
    status: UndoStatus = UndoStatus.ACTIVE,
    rev_class: ReversibilityClass = ReversibilityClass.R2,
    ts: float = 1000.0,
    expires_at: float | None = None,
) -> UndoEntry:
    return UndoEntry(
        id=eid,
        ts=ts,
        server="srv",
        tool="delete_page",
        rev_class=rev_class,
        status=status,
        session_id=session,
        expires_at=expires_at,
    )


class TestAppendGetRecent:
    def test_append_and_get(self) -> None:
        log = UndoLog(":memory:")
        log.append(_entry("a"))
        got = log.get("a")
        assert got is not None
        assert got.id == "a"
        assert got.tool == "delete_page"

    def test_get_missing_returns_none(self) -> None:
        log = UndoLog(":memory:")
        assert log.get("nope") is None

    def test_recent_newest_first(self) -> None:
        log = UndoLog(":memory:")
        log.append(_entry("a", ts=1.0))
        log.append(_entry("b", ts=2.0))
        log.append(_entry("c", ts=3.0))
        recent = log.recent(10)
        assert [e.id for e in recent] == ["c", "b", "a"]

    def test_recent_limit(self) -> None:
        log = UndoLog(":memory:")
        for i in range(5):
            log.append(_entry(f"e{i}", ts=float(i)))
        assert len(log.recent(2)) == 2

    def test_recent_filters_by_session(self) -> None:
        log = UndoLog(":memory:")
        log.append(_entry("a", session="s1"))
        log.append(_entry("b", session="s2"))
        got = log.recent(10, session_id="s1")
        assert [e.id for e in got] == ["a"]


class TestUndoable:
    def test_undoable_only_active_nonexpired(self) -> None:
        log = UndoLog(":memory:")
        log.append(_entry("active", status=UndoStatus.ACTIVE, ts=1.0))
        log.append(_entry("done", status=UndoStatus.UNDONE, ts=2.0))
        log.append(_entry("expired", status=UndoStatus.ACTIVE, ts=3.0, expires_at=1.0))
        ids = [e.id for e in log.undoable(session_id="sess")]
        assert ids == ["active"]


class TestMarkAndExpire:
    def test_mark_updates_status(self) -> None:
        log = UndoLog(":memory:")
        log.append(_entry("a"))
        log.mark("a", UndoStatus.UNDONE)
        assert log.get("a").status == UndoStatus.UNDONE  # type: ignore[union-attr]

    def test_mark_missing_raises(self) -> None:
        log = UndoLog(":memory:")
        with pytest.raises(KeyError):
            log.mark("nope", UndoStatus.UNDONE)

    def test_expire_due_marks_expired(self) -> None:
        log = UndoLog(":memory:")
        log.append(_entry("old", expires_at=100.0))
        log.append(_entry("live", expires_at=10_000.0))
        n = log.expire_due(at=500.0)
        assert n == 1
        assert log.get("old").status == UndoStatus.EXPIRED  # type: ignore[union-attr]
        assert log.get("live").status == UndoStatus.ACTIVE  # type: ignore[union-attr]


class TestStats:
    def test_stats_by_status_and_class(self) -> None:
        log = UndoLog(":memory:")
        log.append(_entry("a", status=UndoStatus.ACTIVE, rev_class=ReversibilityClass.R2))
        log.append(_entry("b", status=UndoStatus.UNDONE, rev_class=ReversibilityClass.R2))
        log.append(_entry("c", status=UndoStatus.ACTIVE, rev_class=ReversibilityClass.R4))
        stats = log.stats()
        assert stats["active"] == 2
        assert stats["undone"] == 1
        assert stats["R2"] == 2
        assert stats["R4"] == 1


class TestDurabilityAcrossReopen:
    def test_entry_persists_after_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "undo.db"
        log = UndoLog(db)
        log.append(_entry("persisted", rev_class=ReversibilityClass.R2))
        log.mark("persisted", UndoStatus.UNDONE)
        log.close()

        reopened = UndoLog(db)
        got = reopened.get("persisted")
        assert got is not None
        assert got.id == "persisted"
        assert got.status == UndoStatus.UNDONE
        assert got.rev_class == ReversibilityClass.R2
        reopened.close()

    def test_context_manager_closes(self, tmp_path: Path) -> None:
        db = tmp_path / "cm.db"
        with UndoLog(db) as log:
            log.append(_entry("x"))
        with UndoLog(db) as log2:
            assert log2.get("x") is not None
