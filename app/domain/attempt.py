"""The Attempt aggregate.

An attempt is the unit a learner improves across. It owns one submission and
at most one evaluation, and it owns its own lifecycle: no service is allowed
to set `status` directly, it can only ask the attempt to make a transition
that the attempt itself decides is legal.

The state machine is where "what happens if evaluation is slow or fails" is
answered. EVALUATING is a real, persisted state rather than the time a request
happens to be blocked, so a slow evaluation is a page the learner can leave
and come back to, and a failed one is a state they can retry from without
retyping the design.

    DRAFT --submit--> SUBMITTED --start--> EVALUATING --complete--> EVALUATED
                                               |
                                               +----fail----> FAILED
                                                                |
                                                    retry (back to EVALUATING)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .errors import IllegalTransition
from .feedback import Evaluation
from .submission import Submission


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AttemptStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (AttemptStatus.EVALUATED, AttemptStatus.FAILED)

    @property
    def label(self) -> str:
        return {
            AttemptStatus.DRAFT: "Draft",
            AttemptStatus.SUBMITTED: "Submitted",
            AttemptStatus.EVALUATING: "Evaluating",
            AttemptStatus.EVALUATED: "Feedback ready",
            AttemptStatus.FAILED: "Evaluation failed",
        }[self]


# The whole lifecycle, in one readable place.
ALLOWED: dict[AttemptStatus, frozenset[AttemptStatus]] = {
    AttemptStatus.DRAFT: frozenset({AttemptStatus.SUBMITTED}),
    AttemptStatus.SUBMITTED: frozenset({AttemptStatus.EVALUATING}),
    AttemptStatus.EVALUATING: frozenset({AttemptStatus.EVALUATED, AttemptStatus.FAILED}),
    AttemptStatus.EVALUATED: frozenset(),
    AttemptStatus.FAILED: frozenset({AttemptStatus.EVALUATING}),
}


@dataclass
class Attempt:
    id: str
    problem_id: str
    learner_id: str
    attempt_no: int
    status: AttemptStatus = AttemptStatus.DRAFT
    submission: Submission | None = None
    evaluation: Evaluation | None = None
    error: str = ""
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def _transition(self, to: AttemptStatus) -> None:
        if to not in ALLOWED[self.status]:
            raise IllegalTransition(
                "Cannot move attempt {} from {} to {}.".format(
                    self.id, self.status.value, to.value
                )
            )
        self.status = to
        self.updated_at = utcnow()

    def submit(self, submission: Submission) -> None:
        """Attach a validated submission and mark the attempt submitted.

        Validation happens before the transition, so a rejected submission
        leaves the attempt in DRAFT and the learner keeps their work.
        """
        submission.validate()
        self._transition(AttemptStatus.SUBMITTED)
        self.submission = submission

    def begin_evaluation(self) -> None:
        self._transition(AttemptStatus.EVALUATING)
        self.error = ""

    def complete_evaluation(self, evaluation: Evaluation) -> None:
        self._transition(AttemptStatus.EVALUATED)
        self.evaluation = evaluation

    def fail_evaluation(self, reason: str) -> None:
        self._transition(AttemptStatus.FAILED)
        self.error = reason

    def retry_evaluation(self) -> None:
        """Re-run evaluation on the submission already held.

        Only legal from FAILED. The submission is untouched, so this costs the
        learner nothing.
        """
        if self.submission is None:
            raise IllegalTransition("Attempt {} has no submission to retry.".format(self.id))
        self._transition(AttemptStatus.EVALUATING)
        self.error = ""

    @property
    def is_pending(self) -> bool:
        return self.status in (AttemptStatus.SUBMITTED, AttemptStatus.EVALUATING)

    @property
    def score_percent(self) -> int | None:
        return self.evaluation.overall_percent if self.evaluation else None
