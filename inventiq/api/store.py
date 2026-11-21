"""Buyer decisions, kept in SQLite: every approve, edit, reject and undo is appended, never overwritten,
so the log doubles as an audit trail. The latest decision per option is the one in force."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
create table if not exists decisions (
    id integer primary key autoincrement,
    option_id text not null,
    action text not null check (action in ('approve', 'edit', 'reject', 'undo')),
    hard integer,
    allot integer,
    budget real,
    risk text,
    note text,
    created_at text not null
);
create index if not exists decisions_option on decisions(option_id, id);
"""


class DecisionStore:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def add(
        self,
        option_id: str,
        action: str,
        hard: int | None = None,
        allot: int | None = None,
        budget: float | None = None,
        risk: str | None = None,
        note: str | None = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            cur = self._db.execute(
                "insert into decisions (option_id, action, hard, allot, budget, risk, note, created_at) "
                "values (?, ?, ?, ?, ?, ?, ?, ?)",
                (option_id, action, hard, allot, budget, risk, note, now),
            )
            self._db.commit()
            row = self._db.execute("select * from decisions where id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def log(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._db.execute("select * from decisions order by id desc limit ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def current(self) -> dict[str, dict]:
        """The decision in force per option (an undo clears it)."""
        with self._lock:
            rows = self._db.execute(
                "select d.* from decisions d join (select option_id, max(id) as id from decisions group by option_id) m "
                "on d.id = m.id"
            ).fetchall()
        return {r["option_id"]: dict(r) for r in rows if r["action"] != "undo"}

    def forced(self) -> dict[str, tuple[int, int]]:
        """Locked plans for the optimiser: approved and edited plans keep their units, rejected ones get none."""
        out = {}
        for oid, r in self.current().items():
            out[oid] = (0, 0) if r["action"] == "reject" else (int(r["hard"] or 0), int(r["allot"] or 0))
        return out

    def clear(self) -> None:
        with self._lock:
            self._db.execute("delete from decisions")
            self._db.commit()
