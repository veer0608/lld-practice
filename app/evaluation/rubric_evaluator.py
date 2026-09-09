"""The deterministic half of evaluation.

What is checkable without a model is narrow but genuinely reliable:

* did the learner name the concepts the problem is actually about, and where
  the criterion is a claim about a type existing, did they name a *class* for
  it rather than a method,
* did they say what each class is responsible for,
* and whatever the submission format itself can check about its own shape,
  which it reports through `structural_notes` rather than being switched on
  here: a stated trade-off, a parse error, a god class, an orphan.

Every finding here cites the learner's own symbol as evidence, and every one
is reproducible - the same submission scores the same tomorrow, with no API
call and no cost. That is what makes it the floor the LLM sits on top of: if
the model is down, a learner still gets feedback that is defensible.

What is deliberately NOT here: anything requiring judgement about whether an
abstraction is *good*. Keyword presence is evidence of coverage, never of
quality, and the messages are worded to keep that distinction visible.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import replace

from app.domain.feedback import DimensionScore, Evaluation, FeedbackItem, Severity
from app.domain.problem import Dimension, MatchScope, Problem, RubricCriterion
from app.domain.submission import Submission

from .evaluator import Evaluator


class RubricEvaluator(Evaluator):
    """Checks a submission against the problem's rubric. No network, no model."""

    name = "rubric"

    def evaluate(self, problem: Problem, submission: Submission) -> Evaluation:
        started = time.perf_counter()
        haystacks = {
            MatchScope.ANYWHERE: submission.symbols(),
            MatchScope.TYPE_NAME: submission.declared_types(),
        }

        items: list[FeedbackItem] = []
        per_dimension: dict[Dimension, list[tuple[float, bool]]] = defaultdict(list)

        for criterion in problem.rubric:
            words = haystacks[criterion.scope]
            met = self._is_met(criterion, words)
            per_dimension[criterion.dimension].append((criterion.weight, met))
            items.append(self._item_for(criterion, met, words))

        # Each format knows what can be checked about its own shape. Asking the
        # submission rather than switching on its type is what makes "a new
        # format needs no evaluator change" true instead of aspirational.
        items.extend(
            replace(note, source=self.name) for note in submission.structural_notes()
        )

        scores = [
            DimensionScore(
                dimension=dim,
                score=(
                    sum(w for w, met in rows if met) / sum(w for w, _ in rows)
                    if sum(w for w, _ in rows)
                    else 0.0
                ),
                met=sum(1 for _, met in rows if met),
                total=len(rows),
            )
            for dim, rows in per_dimension.items()
        ]

        gaps = sum(
            1
            for i in items
            if i.criterion_id is not None and i.severity is Severity.GAP
        )
        return Evaluation(
            items=items,
            scores=scores,
            summary=self._summary(gaps, len(problem.rubric)),
            sources=[self.name],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    # -- checks -------------------------------------------------------

    @staticmethod
    def _is_met(criterion: RubricCriterion, symbols: set[str]) -> bool:
        """A criterion is met when any one keyword phrase is fully present.

        Multi-word keywords require every word, so "parking spot" is not
        satisfied by the word "parking" on its own.
        """
        for keyword in criterion.keywords:
            words = {w.lower() for w in keyword.split()}
            if words and words <= symbols:
                return True
        return False

    def _item_for(
        self, criterion: RubricCriterion, met: bool, symbols: set[str]
    ) -> FeedbackItem:
        if met:
            hit = next(
                (k for k in criterion.keywords if {w.lower() for w in k.split()} <= symbols),
                "",
            )
            return FeedbackItem(
                dimension=criterion.dimension,
                severity=Severity.STRENGTH,
                message="Covered: " + criterion.description,
                evidence="your design names " + repr(hit),
                source=self.name,
                criterion_id=criterion.id,
            )
        where = (
            "no class named " if criterion.scope is MatchScope.TYPE_NAME else "no mention of "
        )
        return FeedbackItem(
            dimension=criterion.dimension,
            severity=Severity.GAP if criterion.required else Severity.SUGGESTION,
            message="Not found in your design: " + criterion.description,
            evidence=where + " / ".join(criterion.keywords[:3]),
            source=self.name,
            criterion_id=criterion.id,
        )

    @staticmethod
    def _summary(gaps: int, total: int) -> str:
        if total == 0:
            return "No rubric configured for this problem."
        if gaps == 0:
            return "Every required concept for this problem appears in your design."
        return "{} required concept{} missing from your design.".format(
            gaps, "" if gaps == 1 else "s"
        )
