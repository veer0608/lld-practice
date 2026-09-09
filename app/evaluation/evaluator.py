"""The evaluator seam.

Everything that judges a design implements this one interface. The attempt
lifecycle, the storage layer and the web layer know `Evaluator` and nothing
else, so a new strategy (a peer review queue, a static-analysis pass, a
different model) is a new class and one line of wiring.

Two rules keep the seam honest:

* an evaluator receives the `Problem` and the `Submission`, never the Attempt.
  Evaluation is a pure function of what was asked and what was handed in, so
  it can be replayed on an old submission later.
* an evaluator returns an `Evaluation` or raises `EvaluationError`. It never
  half-succeeds, and it never mutates anything.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.feedback import Evaluation
from app.domain.problem import Problem
from app.domain.submission import Submission


class EvaluationError(Exception):
    """An evaluator could not produce a result.

    Carries `retryable` so the caller can tell a transient failure (model
    timeout, rate limit) from a permanent one (bad configuration), which is
    what decides whether the learner is offered a retry button.
    """

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class Evaluator(ABC):
    """Judges one submission against one problem."""

    name: str = "evaluator"

    #: Does this evaluator return the same score for the same submission every
    #: time? Only reproducible scores go into the learner's trend, because a
    #: score that drifts draws improvement that did not happen. Default False:
    #: an evaluator has to claim this, rather than have it assumed.
    reproducible: bool = False

    @abstractmethod
    def evaluate(self, problem: Problem, submission: Submission) -> Evaluation:
        """Return feedback, or raise EvaluationError."""

    @property
    def is_available(self) -> bool:
        """Whether this evaluator can run right now.

        The LLM evaluator answers False when no API key is configured, which
        lets the pipeline degrade quietly instead of failing the attempt.
        """
        return True
