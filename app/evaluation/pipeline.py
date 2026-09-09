"""Composing evaluators, and deciding what "failed" means.

The assignment asks what should happen when evaluation is slow or fails. The
answer here is a split the pipeline enforces rather than documents:

* **required** evaluators must succeed. Today that is the rubric, which needs
  no network and cannot rate-limit, so an attempt effectively always gets
  feedback of some kind.
* **optional** evaluators may fail. Today that is the LLM. When it does, the
  learner still gets the deterministic result, flagged `degraded` with the
  reason, plus a retry that costs them nothing because the submission is
  already stored.

That is why the platform never shows a spinner that can end in nothing. The
worst case is weaker feedback with an honest label on it, not a dead end.
"""

from __future__ import annotations

from app.domain.feedback import Evaluation
from app.domain.problem import Problem
from app.domain.submission import Submission

from .evaluator import EvaluationError, Evaluator


class EvaluationPipeline(Evaluator):
    """Runs several evaluators and merges their results into one."""

    name = "pipeline"

    def __init__(
        self,
        required: list[Evaluator] | None = None,
        optional: list[Evaluator] | None = None,
    ) -> None:
        self.required = required or []
        self.optional = optional or []

    def evaluate(self, problem: Problem, submission: Submission) -> Evaluation:
        result = Evaluation()

        for evaluator in self.required:
            result = result.merge(evaluator.evaluate(problem, submission))

        for evaluator in self.optional:
            if not evaluator.is_available:
                result.degraded = True
                result.degraded_reason = self._join(
                    result.degraded_reason,
                    evaluator.name + " is not configured, so this is rubric-only feedback",
                )
                continue
            try:
                result = result.merge(evaluator.evaluate(problem, submission))
            except EvaluationError as exc:
                result.degraded = True
                result.degraded_reason = self._join(
                    result.degraded_reason, evaluator.name + " failed: " + str(exc)
                )
            except Exception as exc:  # defensive: a provider client can raise anything
                result.degraded = True
                result.degraded_reason = self._join(
                    result.degraded_reason,
                    "{} raised {}: {}".format(evaluator.name, type(exc).__name__, exc),
                )

        if not result.scores and not result.items:
            raise EvaluationError("No evaluator produced a result.", retryable=True)
        return result

    @staticmethod
    def _join(existing: str, addition: str) -> str:
        return "; ".join(part for part in (existing, addition) if part)
