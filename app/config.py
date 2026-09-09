"""The composition root.

Every concrete choice the app makes - SQLite or memory, which evaluators run,
threads or inline - is made once, here. Nothing below this file constructs its
own dependencies, which is what makes the whole stack testable by passing
different arguments rather than by patching modules.

The LLM evaluator is optional by construction. With no API key the platform
still runs the full loop on rubric feedback and says so, rather than failing to
start. A demo that dies because a key is missing is not a demo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.content.problems import default_problem_repository
from app.evaluation.evaluator import Evaluator
from app.evaluation.llm_client import GeminiClient
from app.evaluation.llm_evaluator import LLMEvaluator
from app.evaluation.pipeline import EvaluationPipeline
from app.evaluation.rubric_evaluator import RubricEvaluator
from app.services.practice import PracticeService
from app.services.runner import TaskRunner, ThreadRunner
from app.storage.memory_store import InMemoryAttemptRepository
from app.storage.repositories import AttemptRepository
from app.storage.sqlite_store import SqliteAttemptRepository

DEFAULT_LEARNER = "demo-learner"


@dataclass
class Settings:
    # Anchored to the project root, not the working directory: uvicorn is often
    # started from somewhere else, and a database that moves with the CWD looks
    # exactly like data loss.
    db_path: str = os.environ.get(
        "LLD_DB", str(Path(__file__).resolve().parent.parent / "data" / "lld_practice.db")
    )
    use_llm: bool = os.environ.get("LLD_USE_LLM", "1") != "0"
    in_memory: bool = os.environ.get("LLD_IN_MEMORY", "0") == "1"


def build_evaluator(use_llm: bool = True) -> EvaluationPipeline:
    """Rubric is required, the model is optional. That ordering is the design.

    See `pipeline.py`: a required evaluator failing fails the attempt, an
    optional one failing only degrades it.

    A missing API key does NOT drop the evaluator here. It is wired in and
    reports `is_available` False, so the pipeline marks the result degraded and
    the learner is told the feedback is rubric-only. Filtering it out at
    construction time instead would make the platform quietly weaker with no
    signal, and would leave the pipeline's "not configured" branch unreachable
    in production while still passing its test.

    `use_llm=False` is the other case: the operator turned the model off on
    purpose, so there is nothing to report and nothing is wired.
    """
    optional: list[Evaluator] = [LLMEvaluator(GeminiClient())] if use_llm else []
    return EvaluationPipeline(required=[RubricEvaluator()], optional=optional)


def build_service(
    settings: Settings | None = None,
    runner: TaskRunner | None = None,
) -> PracticeService:
    settings = settings or Settings()
    attempts: AttemptRepository = (
        InMemoryAttemptRepository()
        if settings.in_memory
        else SqliteAttemptRepository(settings.db_path)
    )
    return PracticeService(
        problems=default_problem_repository(),
        attempts=attempts,
        evaluator=build_evaluator(settings.use_llm),
        runner=runner or ThreadRunner(),
    )
