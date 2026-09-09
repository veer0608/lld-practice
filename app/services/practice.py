"""The practice loop, as one service.

Choose problem -> design -> submit -> evaluate -> review -> try again.

This is the only object the web layer talks to. It orchestrates and it does not
decide: the legality of every state change belongs to `Attempt`, the judgement
belongs to the evaluators, and the storage format belongs to the repositories.
Keeping the service thin is what stops it becoming the god class the platform
teaches learners to avoid.
"""

from __future__ import annotations

import uuid

from app.domain.attempt import Attempt, AttemptStatus
from app.domain.errors import NotFound
from app.domain.problem import Problem
from app.domain.submission import Submission
from app.evaluation.evaluator import EvaluationError, Evaluator
from app.storage.repositories import AttemptRepository, ProblemRepository

from .runner import InlineRunner, TaskRunner


class PracticeService:
    def __init__(
        self,
        problems: ProblemRepository,
        attempts: AttemptRepository,
        evaluator: Evaluator,
        runner: TaskRunner | None = None,
    ) -> None:
        self.problems = problems
        self.attempts = attempts
        self.evaluator = evaluator
        self.runner = runner or InlineRunner()

    # -- problems -----------------------------------------------------

    def list_problems(self) -> list[Problem]:
        return self.problems.list()

    def get_problem(self, problem_id: str) -> Problem:
        problem = self.problems.get(problem_id)
        if problem is None:
            raise NotFound("No problem with id " + repr(problem_id))
        return problem

    # -- the loop -----------------------------------------------------

    def start_attempt(self, learner_id: str, problem_id: str) -> Attempt:
        problem = self.get_problem(problem_id)
        attempt = Attempt(
            id=uuid.uuid4().hex[:12],
            problem_id=problem.id,
            learner_id=learner_id,
            attempt_no=self.attempts.count_for(learner_id, problem.id) + 1,
        )
        self.attempts.save(attempt)
        return attempt

    def submit(self, attempt_id: str, submission: Submission) -> Attempt:
        """Accept a submission and schedule its evaluation.

        Returns as soon as the submission is durable. The learner is not made
        to wait for a model, and if the process dies here the attempt is
        recoverable: it is SUBMITTED with its design intact, which is a state
        `resume_pending` knows how to pick back up.
        """
        attempt = self.get_attempt(attempt_id)
        attempt.submit(submission)
        self.attempts.save(attempt)
        self._schedule(attempt.id)
        return attempt

    def retry_evaluation(self, attempt_id: str) -> Attempt:
        """Re-run evaluation on a failed attempt. The design is not retyped."""
        attempt = self.get_attempt(attempt_id)
        attempt.retry_evaluation()
        self.attempts.save(attempt)
        self._schedule(attempt.id, already_started=True)
        return attempt

    def _schedule(self, attempt_id: str, already_started: bool = False) -> None:
        self.runner.submit(lambda: self.run_evaluation(attempt_id, already_started))

    def run_evaluation(self, attempt_id: str, already_started: bool = False) -> Attempt:
        """Run the pipeline and record the outcome.

        Reloads the attempt rather than closing over it, because this may run on
        another thread minutes after `submit` returned. Every exit path writes a
        terminal state, so an attempt can never be left showing "evaluating"
        forever while nothing is running.
        """
        attempt = self.get_attempt(attempt_id)
        if not already_started:
            attempt.begin_evaluation()
            self.attempts.save(attempt)

        if attempt.submission is None:  # defensive: unreachable via submit()
            attempt.fail_evaluation("Attempt has no submission.")
            self.attempts.save(attempt)
            return attempt

        try:
            problem = self.get_problem(attempt.problem_id)
            evaluation = self.evaluator.evaluate(problem, attempt.submission)
        except EvaluationError as exc:
            attempt.fail_evaluation(str(exc))
        except Exception as exc:  # a bug here must not strand the attempt
            attempt.fail_evaluation("{}: {}".format(type(exc).__name__, exc))
        else:
            attempt.complete_evaluation(evaluation)

        self.attempts.save(attempt)
        return attempt

    def resume_pending(self, learner_id: str) -> list[Attempt]:
        """Re-schedule attempts left mid-flight by a restart.

        A thread pool does not survive a process exit, so anything still in
        SUBMITTED or EVALUATING after a restart would sit there forever. This is
        the cheap version of a durable queue: correct for a monolith, and the
        place a real queue would replace.
        """
        stuck = [a for a in self.attempts.list_for_learner(learner_id) if a.is_pending]
        for attempt in stuck:
            if attempt.status is AttemptStatus.EVALUATING:
                # Already past begin_evaluation, so do not transition again.
                self._schedule(attempt.id, already_started=True)
            else:
                self._schedule(attempt.id)
        return stuck

    # -- reading ------------------------------------------------------

    def get_attempt(self, attempt_id: str) -> Attempt:
        attempt = self.attempts.get(attempt_id)
        if attempt is None:
            raise NotFound("No attempt with id " + repr(attempt_id))
        return attempt

    def history(self, learner_id: str, problem_id: str | None = None) -> list[Attempt]:
        return self.attempts.list_for_learner(learner_id, problem_id)

    def progress(self, learner_id: str, problem_id: str) -> list[int]:
        """Scores across attempts, oldest first. The point of the whole product.

        A learner improving is the only signal that says the feedback worked, so
        it is a first-class query rather than something a template computes.
        """
        attempts = sorted(
            self.attempts.list_for_learner(learner_id, problem_id),
            key=lambda a: a.attempt_no,
        )
        return [a.score_percent for a in attempts if a.score_percent is not None]
