"""Composition and the practice loop, including the failure paths."""

from __future__ import annotations

import pytest

from app.domain.attempt import AttemptStatus
from app.domain.errors import NotFound
from app.domain.feedback import DimensionScore, Evaluation, FeedbackItem, Severity
from app.domain.problem import Dimension
from app.evaluation.evaluator import EvaluationError, Evaluator
from app.evaluation.pipeline import EvaluationPipeline
from app.evaluation.rubric_evaluator import RubricEvaluator

from .conftest import build_service


class StubEvaluator(Evaluator):
    name = "stub"

    def __init__(self, score: float = 0.5, available: bool = True) -> None:
        self.score = score
        self._available = available
        self.calls = 0

    @property
    def is_available(self) -> bool:
        return self._available

    def evaluate(self, problem, submission):
        self.calls += 1
        return Evaluation(
            items=[
                FeedbackItem(Dimension.ABSTRACTION, Severity.SUGGESTION, "stub says hi", source="stub")
            ],
            scores=[DimensionScore(Dimension.ABSTRACTION, self.score)],
            summary="stub summary",
            sources=["stub"],
        )


class BrokenEvaluator(Evaluator):
    name = "broken"

    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc or EvaluationError("model timed out", retryable=True)

    def evaluate(self, problem, submission):
        raise self.exc


class FlakyEvaluator(Evaluator):
    """Fails once, then succeeds. Stands in for a rate-limited model."""

    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, problem, submission):
        self.calls += 1
        if self.calls == 1:
            raise EvaluationError("rate limited", retryable=True)
        return Evaluation(
            scores=[DimensionScore(Dimension.ABSTRACTION, 0.9)],
            summary="second time lucky",
            sources=["flaky"],
        )


# -- pipeline ---------------------------------------------------------


def test_scores_from_two_evaluators_are_averaged_per_dimension(problem, good_design):
    pipeline = EvaluationPipeline(
        required=[StubEvaluator(score=1.0)], optional=[StubEvaluator(score=0.0)]
    )
    result = pipeline.evaluate(problem, good_design)
    assert [s.score for s in result.scores] == [0.5]
    assert len(result.items) == 2  # agreement is kept, not deduplicated
    assert result.sources == ["stub", "stub"]


def test_an_optional_evaluator_failing_degrades_instead_of_failing(problem, good_design):
    pipeline = EvaluationPipeline(required=[RubricEvaluator()], optional=[BrokenEvaluator()])
    result = pipeline.evaluate(problem, good_design)

    assert result.degraded is True
    assert "model timed out" in result.degraded_reason
    assert result.scores  # the learner still gets the rubric result
    assert "rubric" in result.sources


def test_an_unconfigured_optional_evaluator_says_so_without_being_called(problem, good_design):
    stub = StubEvaluator(available=False)
    result = EvaluationPipeline(required=[RubricEvaluator()], optional=[stub]).evaluate(
        problem, good_design
    )
    assert stub.calls == 0
    assert result.degraded
    assert "not configured" in result.degraded_reason


def test_a_required_evaluator_failing_fails_the_evaluation(problem, good_design):
    pipeline = EvaluationPipeline(required=[BrokenEvaluator()])
    with pytest.raises(EvaluationError):
        pipeline.evaluate(problem, good_design)


def test_a_non_evaluation_exception_from_an_optional_evaluator_is_contained(problem, good_design):
    pipeline = EvaluationPipeline(
        required=[RubricEvaluator()], optional=[BrokenEvaluator(RuntimeError("socket exploded"))]
    )
    result = pipeline.evaluate(problem, good_design)
    assert result.degraded
    assert "RuntimeError" in result.degraded_reason


# -- service ----------------------------------------------------------


def test_the_full_loop_produces_feedback(service, good_design):
    attempt = service.start_attempt("veer", "parking-lot")
    service.submit(attempt.id, good_design)

    stored = service.get_attempt(attempt.id)
    assert stored.status is AttemptStatus.EVALUATED
    assert stored.evaluation is not None
    assert stored.score_percent is not None


def test_attempts_are_numbered_per_learner_and_problem(service, good_design):
    first = service.start_attempt("veer", "parking-lot")
    service.submit(first.id, good_design)
    second = service.start_attempt("veer", "parking-lot")
    other_problem = service.start_attempt("veer", "elevator")
    other_learner = service.start_attempt("someone-else", "parking-lot")

    assert (first.attempt_no, second.attempt_no) == (1, 2)
    assert other_problem.attempt_no == 1
    assert other_learner.attempt_no == 1


def test_history_is_newest_first_and_scoped_to_the_problem(service, good_design):
    a = service.start_attempt("veer", "parking-lot")
    service.submit(a.id, good_design)
    b = service.start_attempt("veer", "elevator")

    everything = service.history("veer")
    assert {x.id for x in everything} == {a.id, b.id}
    assert [x.id for x in service.history("veer", "elevator")] == [b.id]


def test_a_failed_evaluation_leaves_a_retryable_attempt(good_design):
    flaky = FlakyEvaluator()
    service = build_service(evaluator=EvaluationPipeline(required=[flaky]))

    attempt = service.start_attempt("veer", "parking-lot")
    service.submit(attempt.id, good_design)

    failed = service.get_attempt(attempt.id)
    assert failed.status is AttemptStatus.FAILED
    assert "rate limited" in failed.error
    assert failed.submission is not None  # the design survived

    service.retry_evaluation(attempt.id)
    recovered = service.get_attempt(attempt.id)
    assert recovered.status is AttemptStatus.EVALUATED
    assert recovered.evaluation.summary == "second time lucky"


def test_a_bug_in_an_evaluator_cannot_strand_an_attempt(good_design):
    """The worst case must still be a terminal state, never a stuck spinner."""
    service = build_service(
        evaluator=EvaluationPipeline(required=[BrokenEvaluator(ZeroDivisionError("oops"))])
    )
    attempt = service.start_attempt("veer", "parking-lot")
    service.submit(attempt.id, good_design)

    stored = service.get_attempt(attempt.id)
    assert stored.status is AttemptStatus.FAILED
    assert "ZeroDivisionError" in stored.error


def test_resume_pending_picks_up_work_a_restart_dropped(good_design):
    """Simulates a process dying between submit and evaluate."""
    service = build_service()
    attempt = service.start_attempt("veer", "parking-lot")
    attempt.submit(good_design)
    service.attempts.save(attempt)  # saved as SUBMITTED, evaluation never scheduled

    assert service.get_attempt(attempt.id).status is AttemptStatus.SUBMITTED
    resumed = service.resume_pending("veer")

    assert [a.id for a in resumed] == [attempt.id]
    assert service.get_attempt(attempt.id).status is AttemptStatus.EVALUATED


def test_resume_pending_does_not_re_transition_an_evaluating_attempt(good_design):
    service = build_service()
    attempt = service.start_attempt("veer", "parking-lot")
    attempt.submit(good_design)
    attempt.begin_evaluation()
    service.attempts.save(attempt)  # died mid-evaluation

    service.resume_pending("veer")
    assert service.get_attempt(attempt.id).status is AttemptStatus.EVALUATED


def test_progress_tracks_improvement_across_attempts(service, good_design, thin_design):
    weak = service.start_attempt("veer", "parking-lot")
    service.submit(weak.id, thin_design)
    strong = service.start_attempt("veer", "parking-lot")
    service.submit(strong.id, good_design)

    progress = service.progress("veer", "parking-lot")
    assert len(progress) == 2
    assert progress[1] > progress[0]


def test_unknown_ids_raise_not_found(service):
    with pytest.raises(NotFound):
        service.get_attempt("nope")
    with pytest.raises(NotFound):
        service.get_problem("travelling-salesman")


# -- composition root -------------------------------------------------


def test_a_missing_api_key_degrades_visibly_rather_than_silently(monkeypatch, tmp_path, problem, good_design):
    """The no-key path must reach the learner, not vanish at construction."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.evaluation.llm_client.load_api_key", lambda: None)

    from app.config import build_evaluator

    result = build_evaluator(use_llm=True).evaluate(problem, good_design)
    assert result.degraded is True
    assert "not configured" in result.degraded_reason
    assert result.sources == ["rubric"]


def test_turning_the_model_off_deliberately_is_not_a_degradation(problem, good_design):
    from app.config import build_evaluator

    result = build_evaluator(use_llm=False).evaluate(problem, good_design)
    assert result.degraded is False
    assert result.sources == ["rubric"]
