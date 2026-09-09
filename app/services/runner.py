"""How work that might be slow gets off the request thread.

An LLM call takes seconds and can hang. Doing it inside the POST that submits
a design means a learner watching a browser spinner they cannot leave, and a
timeout that loses their work.

So submission and evaluation are separated by a `TaskRunner`. The web app uses
a small thread pool; the tests use `InlineRunner`, which runs the work
immediately on the calling thread. Same service code, no `if testing` branch,
and the test suite stays deterministic with no sleeps in it.

A thread pool is the honest choice at this size. If evaluation ever needed to
survive a restart, this is the seam a real queue would be swapped in behind,
and nothing above it would change.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Protocol


class TaskRunner(Protocol):
    def submit(self, fn: Callable[[], None]) -> None:  # pragma: no cover - protocol
        ...


class InlineRunner:
    """Runs the task immediately. Used by tests and by the CLI demo."""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()


class ThreadRunner:
    """Runs the task on a small pool, so the request returns straight away."""

    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="eval")

    def submit(self, fn: Callable[[], None]) -> None:
        self._pool.submit(fn)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)
