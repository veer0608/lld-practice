"""The attempt lifecycle. Every illegal edge is a test, not a comment."""

from __future__ import annotations

import pytest

from app.domain.attempt import Attempt, AttemptStatus
from app.domain.errors import IllegalTransition, InvalidSubmission
from app.domain.feedback import Evaluation
from app.domain.submission import DesignSubmission


def make_attempt() -> Attempt:
    return Attempt(id="a1", problem_id="parking-lot", learner_id="veer", attempt_no=1)


def test_happy_path_walks_draft_to_evaluated(good_design):
    attempt = make_attempt()
    attempt.submit(good_design)
    assert attempt.status is AttemptStatus.SUBMITTED

    attempt.begin_evaluation()
    assert attempt.status is AttemptStatus.EVALUATING

    attempt.complete_evaluation(Evaluation(summary="ok"))
    assert attempt.status is AttemptStatus.EVALUATED
    assert attempt.status.is_terminal


def test_cannot_evaluate_something_never_submitted():
    with pytest.raises(IllegalTransition):
        make_attempt().begin_evaluation()


def test_cannot_resubmit_an_evaluated_attempt(good_design):
    attempt = make_attempt()
    attempt.submit(good_design)
    attempt.begin_evaluation()
    attempt.complete_evaluation(Evaluation())
    with pytest.raises(IllegalTransition):
        attempt.submit(good_design)


def test_a_rejected_submission_leaves_the_attempt_in_draft():
    attempt = make_attempt()
    with pytest.raises(InvalidSubmission):
        attempt.submit(DesignSubmission(classes=[]))
    # The learner keeps their work and can fix and resubmit.
    assert attempt.status is AttemptStatus.DRAFT
    assert attempt.submission is None


def test_failure_is_retryable_and_keeps_the_submission(good_design):
    attempt = make_attempt()
    attempt.submit(good_design)
    attempt.begin_evaluation()
    attempt.fail_evaluation("model timed out")

    assert attempt.status is AttemptStatus.FAILED
    assert attempt.error == "model timed out"

    attempt.retry_evaluation()
    assert attempt.status is AttemptStatus.EVALUATING
    assert attempt.error == ""
    assert attempt.submission is good_design


def test_retry_is_not_a_way_to_re_evaluate_a_finished_attempt(good_design):
    attempt = make_attempt()
    attempt.submit(good_design)
    attempt.begin_evaluation()
    attempt.complete_evaluation(Evaluation())
    with pytest.raises(IllegalTransition):
        attempt.retry_evaluation()
