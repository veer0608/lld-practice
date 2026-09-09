"""The judgement half of evaluation.

The rubric evaluator can tell you a concept is absent. It cannot tell you that
`ParkingLot.assign_spot` should have been `PricingStrategy`'s job, because that
needs an opinion about responsibility, and there is no keyword for it.

So the split this platform draws is: **deterministic where the answer is a
fact, LLM where the answer is a judgement.** Coverage, presence, structure and
parse errors are facts. Whether an abstraction earns its place is a judgement.

Two things keep the judgement half honest:

* the model is told there is no reference solution, so it grades the design the
  learner actually wrote rather than the one it would have written,
* every item must carry a verbatim quote from the submission, and items whose
  evidence is not found in the submission are dropped here, not shown. That is
  the cheapest available check on invention, and it runs on our side.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from app.domain.feedback import DimensionScore, Evaluation, FeedbackItem, Severity
from app.domain.problem import Dimension, Problem
from app.domain.submission import Submission, split_words

from .evaluator import EvaluationError, Evaluator
from .llm_client import GeminiClient, LLMClient, LLMUnavailable

PROMPT_PATH = Path(__file__).parent / "prompts" / "design_review.md"

# A quote is accepted as real if this share of its words appear in the
# submission. Not 1.0: models normalise whitespace and casing, and rejecting a
# true observation over a stripped comma helps nobody.
EVIDENCE_OVERLAP = 0.6
MIN_EVIDENCE_WORDS = 3


class LLMEvaluator(Evaluator):
    """Asks a model for design judgement, then verifies what comes back."""

    name = "llm"

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or GeminiClient()

    @property
    def is_available(self) -> bool:
        configured = getattr(self.client, "configured", True)
        return bool(configured)

    def evaluate(self, problem: Problem, submission: Submission) -> Evaluation:
        started = time.perf_counter()
        prompt = self.build_prompt(problem, submission)

        try:
            raw = self.client.complete(prompt)
        except LLMUnavailable as exc:
            raise EvaluationError(str(exc), retryable=True) from exc

        data = self._parse(raw)
        items, dropped = self._items_from(data, problem, submission)
        scores = self._scores_from(data, problem)

        summary = str(data.get("summary", "")).strip()
        if dropped:
            summary = (summary + " ").strip() + " ({} unsupported observation{} withheld.)".format(
                dropped, "" if dropped == 1 else "s"
            )

        return Evaluation(
            items=items,
            scores=scores,
            summary=summary,
            sources=[self.name],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    # -- prompt -------------------------------------------------------

    def build_prompt(self, problem: Problem, submission: Submission) -> str:
        dimensions = ", ".join(d.value for d in Dimension)
        template = PROMPT_PATH.read_text(encoding="utf-8")
        fields = {
            "problem_title": problem.title,
            "problem_statement": problem.statement,
            "requirements": "\n".join("- " + r for r in problem.requirements),
            "submission_kind": submission.kind,
            "submission": submission.render_for_evaluation(),
            "dimensions": dimensions,
        }
        for key, value in fields.items():
            template = template.replace("{{" + key + "}}", value)
        return template

    # -- parsing ------------------------------------------------------

    @staticmethod
    def _parse(raw: str) -> dict:
        """Take the JSON object out of the response, fenced or not."""
        text = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise EvaluationError(
                "Model did not return JSON: " + repr(raw[:160]), retryable=True
            )
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise EvaluationError(
                "Model returned malformed JSON: " + str(exc), retryable=True
            ) from exc
        if not isinstance(data, dict):
            raise EvaluationError("Model returned JSON that is not an object.", retryable=True)
        return data

    def _items_from(
        self, data: dict, problem: Problem, submission: Submission
    ) -> tuple[list[FeedbackItem], int]:
        haystack = submission.symbols()
        items: list[FeedbackItem] = []
        dropped = 0

        for row in data.get("items") or []:
            if not isinstance(row, dict):
                dropped += 1
                continue
            dimension = self._dimension(row.get("dimension"))
            severity = self._severity(row.get("severity"))
            message = str(row.get("message", "")).strip()
            evidence = str(row.get("evidence", "")).strip()
            if not message or dimension is None or not evidence:
                dropped += 1
                continue
            if not self._evidence_supported(evidence, haystack):
                dropped += 1
                continue
            items.append(
                FeedbackItem(
                    dimension=dimension,
                    severity=severity,
                    message=message,
                    evidence=evidence,
                    source=self.name,
                )
            )
        return items, dropped

    @staticmethod
    def _evidence_supported(evidence: str, haystack: set[str]) -> bool:
        """Is this quote actually in the learner's submission?

        Short quotes are waved through - a two-word quote carries no signal
        either way, and the message still has to stand on its own.
        """
        words = [w for w in split_words(evidence) if len(w) > 2]
        if len(words) < MIN_EVIDENCE_WORDS:
            return True
        hits = sum(1 for w in words if w in haystack)
        return hits / len(words) >= EVIDENCE_OVERLAP

    def _scores_from(self, data: dict, problem: Problem) -> list[DimensionScore]:
        scores: list[DimensionScore] = []
        seen: set[Dimension] = set()
        for row in data.get("dimensions") or []:
            if not isinstance(row, dict):
                continue
            dimension = self._dimension(row.get("dimension"))
            if dimension is None or dimension in seen:
                continue
            try:
                value = float(row.get("score", 0.0))
            except (TypeError, ValueError):
                continue
            seen.add(dimension)
            scores.append(DimensionScore(dimension, min(1.0, max(0.0, value))))
        if not scores:
            raise EvaluationError("Model returned no usable dimension scores.", retryable=True)
        return scores

    @staticmethod
    def _dimension(value: object) -> Dimension | None:
        try:
            return Dimension(str(value).strip().lower())
        except ValueError:
            return None

    @staticmethod
    def _severity(value: object) -> Severity:
        try:
            return Severity(str(value).strip().lower())
        except ValueError:
            return Severity.SUGGESTION
