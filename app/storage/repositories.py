"""Storage seams.

The domain and the services depend on these two interfaces and never on
SQLite. That keeps the aggregate free of persistence concerns and lets the
tests run against an in-memory implementation with no schema and no temp
files, which is why the test suite is fast enough to actually run.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.attempt import Attempt
from app.domain.problem import Problem


class ProblemRepository(ABC):
    """Problems are authored content, so this side is read-only."""

    @abstractmethod
    def list(self) -> list[Problem]:
        ...

    @abstractmethod
    def get(self, problem_id: str) -> Problem | None:
        ...


class AttemptRepository(ABC):
    @abstractmethod
    def save(self, attempt: Attempt) -> None:
        """Insert or replace. The Attempt owns its id, so this is idempotent."""

    @abstractmethod
    def get(self, attempt_id: str) -> Attempt | None:
        ...

    @abstractmethod
    def list_for_learner(self, learner_id: str, problem_id: str | None = None) -> list[Attempt]:
        """Newest first. Filtered to one problem when `problem_id` is given."""

    @abstractmethod
    def count_for(self, learner_id: str, problem_id: str) -> int:
        """How many attempts exist, used to number the next one."""
