"""SQLite persistence. One file, one table, no ORM.

A monolith with a single writer does not need more than this, and the
assignment explicitly asks not to turn the exercise into infrastructure work.
The interesting property is that this file is the only place in the project
that knows SQL: swapping it for Postgres later means writing one more
`AttemptRepository`, not touching the domain.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.domain.attempt import Attempt, AttemptStatus
from app.domain.submission import Submission

from .mapping import evaluation_from_json, evaluation_to_json, iso, parse_iso
from .repositories import AttemptRepository

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id           TEXT PRIMARY KEY,
    problem_id   TEXT NOT NULL,
    learner_id   TEXT NOT NULL,
    attempt_no   INTEGER NOT NULL,
    status       TEXT NOT NULL,
    submission   TEXT,
    evaluation   TEXT,
    error        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_learner
    ON attempts (learner_id, problem_id, created_at DESC);
"""


class SqliteAttemptRepository(AttemptRepository):
    def __init__(self, path: str | Path = "lld_practice.db") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because FastAPI runs the background evaluation
        # on a worker thread. Writes are serialised by SQLite's own lock, and at
        # this scale that is the right amount of concurrency control.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save(self, attempt: Attempt) -> None:
        self._conn.execute(
            """
            INSERT INTO attempts
                (id, problem_id, learner_id, attempt_no, status, submission,
                 evaluation, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status     = excluded.status,
                submission = excluded.submission,
                evaluation = excluded.evaluation,
                error      = excluded.error,
                updated_at = excluded.updated_at
            """,
            (
                attempt.id,
                attempt.problem_id,
                attempt.learner_id,
                attempt.attempt_no,
                attempt.status.value,
                attempt.submission.serialise() if attempt.submission else None,
                evaluation_to_json(attempt.evaluation),
                attempt.error,
                iso(attempt.created_at),
                iso(attempt.updated_at),
            ),
        )
        self._conn.commit()

    def get(self, attempt_id: str) -> Attempt | None:
        row = self._conn.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return self._to_attempt(row) if row else None

    def list_for_learner(
        self, learner_id: str, problem_id: str | None = None
    ) -> list[Attempt]:
        if problem_id:
            rows = self._conn.execute(
                "SELECT * FROM attempts WHERE learner_id = ? AND problem_id = ?"
                " ORDER BY created_at DESC, attempt_no DESC",
                (learner_id, problem_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM attempts WHERE learner_id = ?"
                " ORDER BY created_at DESC, attempt_no DESC",
                (learner_id,),
            ).fetchall()
        return [self._to_attempt(r) for r in rows]

    def count_for(self, learner_id: str, problem_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE learner_id = ? AND problem_id = ?",
            (learner_id, problem_id),
        ).fetchone()
        return int(row["n"])

    @staticmethod
    def _to_attempt(row: sqlite3.Row) -> Attempt:
        return Attempt(
            id=row["id"],
            problem_id=row["problem_id"],
            learner_id=row["learner_id"],
            attempt_no=row["attempt_no"],
            status=AttemptStatus(row["status"]),
            submission=Submission.deserialise(row["submission"]) if row["submission"] else None,
            evaluation=evaluation_from_json(row["evaluation"]),
            error=row["error"] or "",
            created_at=parse_iso(row["created_at"]),
            updated_at=parse_iso(row["updated_at"]),
        )
