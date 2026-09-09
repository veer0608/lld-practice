"""In-memory repositories, for tests and for a throwaway demo run.

Round-trips through the same `mapping` functions as SQLite rather than storing
live objects, so a test that passes here would also survive persistence. An
in-memory fake that hands back the identical object hides exactly the bugs it
should be catching.
"""

from __future__ import annotations

from app.domain.attempt import Attempt, AttemptStatus
from app.domain.problem import Problem
from app.domain.submission import Submission

from .mapping import evaluation_from_json, evaluation_to_json, iso, parse_iso
from .repositories import AttemptRepository, ProblemRepository


class InMemoryProblemRepository(ProblemRepository):
    def __init__(self, problems: list[Problem]) -> None:
        self._problems = {p.id: p for p in problems}

    def list(self) -> list[Problem]:
        return list(self._problems.values())

    def get(self, problem_id: str) -> Problem | None:
        return self._problems.get(problem_id)


class InMemoryAttemptRepository(AttemptRepository):
    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def save(self, attempt: Attempt) -> None:
        self._rows[attempt.id] = {
            "id": attempt.id,
            "problem_id": attempt.problem_id,
            "learner_id": attempt.learner_id,
            "attempt_no": attempt.attempt_no,
            "status": attempt.status.value,
            "submission": attempt.submission.serialise() if attempt.submission else None,
            "evaluation": evaluation_to_json(attempt.evaluation),
            "error": attempt.error,
            "created_at": iso(attempt.created_at),
            "updated_at": iso(attempt.updated_at),
        }

    def get(self, attempt_id: str) -> Attempt | None:
        row = self._rows.get(attempt_id)
        return self._hydrate(row) if row else None

    def list_for_learner(
        self, learner_id: str, problem_id: str | None = None
    ) -> list[Attempt]:
        rows = [
            r
            for r in self._rows.values()
            if r["learner_id"] == learner_id
            and (problem_id is None or r["problem_id"] == problem_id)
        ]
        rows.sort(key=lambda r: (r["created_at"], r["attempt_no"]), reverse=True)
        return [self._hydrate(r) for r in rows]

    def count_for(self, learner_id: str, problem_id: str) -> int:
        return sum(
            1
            for r in self._rows.values()
            if r["learner_id"] == learner_id and r["problem_id"] == problem_id
        )

    @staticmethod
    def _hydrate(row: dict) -> Attempt:
        return Attempt(
            id=row["id"],
            problem_id=row["problem_id"],
            learner_id=row["learner_id"],
            attempt_no=row["attempt_no"],
            status=AttemptStatus(row["status"]),
            submission=Submission.deserialise(row["submission"]) if row["submission"] else None,
            evaluation=evaluation_from_json(row["evaluation"]),
            error=row["error"],
            created_at=parse_iso(row["created_at"]),
            updated_at=parse_iso(row["updated_at"]),
        )
