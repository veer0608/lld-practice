"""The deterministic half of evaluation.

What is checkable without a model is narrow but genuinely reliable:

* did the learner name the concepts the problem is actually about, and where
  the criterion is a claim about a type existing, did they name a *class* for
  it rather than a method,
* did they say what each class is responsible for,
* did they state a trade-off at all,
* does the submission parse, if it is code,
* and a crude god-class signal: one class holding most of the methods.

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

from app.domain.feedback import DimensionScore, Evaluation, FeedbackItem, Severity
from app.domain.problem import Dimension, MatchScope, Problem, RubricCriterion
from app.domain.submission import CodeSubmission, DesignSubmission, Submission, TextSubmission

from .evaluator import Evaluator

GOD_CLASS_SHARE = 0.6
MIN_CLASSES_FOR_GOD_CHECK = 3


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

        items.extend(self._structural_checks(submission))

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

    def _structural_checks(self, submission: Submission) -> list[FeedbackItem]:
        """Format-specific checks that need no rubric.

        Each branch reads the submission through its own type rather than
        through a flag on a single blob, which is the point of having distinct
        Submission subclasses at all.
        """
        items: list[FeedbackItem] = []

        if isinstance(submission, DesignSubmission):
            if not submission.trade_offs.strip():
                items.append(
                    FeedbackItem(
                        dimension=Dimension.TRADE_OFFS,
                        severity=Severity.GAP,
                        message=(
                            "No trade-off stated. Any LLD answer that could not have "
                            "gone another way is not a design decision yet."
                        ),
                        source=self.name,
                    )
                )
            items.extend(self._god_class_check(submission))
            items.extend(self._orphan_check(submission))

        elif isinstance(submission, CodeSubmission):
            error = submission.parse_error()
            if error:
                items.append(
                    FeedbackItem(
                        dimension=Dimension.ABSTRACTION,
                        severity=Severity.SUGGESTION,
                        message=(
                            "Your code did not parse, so structural checks fell back to "
                            "plain text matching and may be less accurate."
                        ),
                        evidence=error,
                        source=self.name,
                    )
                )

        elif isinstance(submission, TextSubmission):
            items.append(
                FeedbackItem(
                    dimension=Dimension.RESPONSIBILITY,
                    severity=Severity.SUGGESTION,
                    message=(
                        "Prose submissions can only be checked shallowly. Re-submitting "
                        "as a class design gets you responsibility-level feedback."
                    ),
                    source=self.name,
                )
            )

        return items

    def _god_class_check(self, submission: DesignSubmission) -> list[FeedbackItem]:
        total = sum(len(c.methods) for c in submission.classes)
        if total < 4 or len(submission.classes) < MIN_CLASSES_FOR_GOD_CHECK:
            return []
        biggest = max(submission.classes, key=lambda c: len(c.methods))
        share = len(biggest.methods) / total
        if share < GOD_CLASS_SHARE:
            return []
        return [
            FeedbackItem(
                dimension=Dimension.RESPONSIBILITY,
                severity=Severity.SUGGESTION,
                message=(
                    biggest.name
                    + " holds most of the behaviour in your design. Check whether it is "
                    "coordinating or actually doing the work itself."
                ),
                evidence="{} of {} methods ({}%) sit on {}".format(
                    len(biggest.methods), total, round(share * 100), biggest.name
                ),
                source=self.name,
            )
        ]

    def _orphan_check(self, submission: DesignSubmission) -> list[FeedbackItem]:
        """Classes nobody collaborates with and which collaborate with nobody."""
        if len(submission.classes) < MIN_CLASSES_FOR_GOD_CHECK:
            return []
        named = {c.lower() for cls in submission.classes for c in cls.collaborators}
        orphans = [
            c.name
            for c in submission.classes
            if not c.collaborators and c.name.lower() not in named
        ]
        if not orphans:
            return []
        return [
            FeedbackItem(
                dimension=Dimension.RELATIONSHIPS,
                severity=Severity.SUGGESTION,
                message=(
                    "These classes are not connected to anything: "
                    + ", ".join(sorted(orphans))
                    + ". Say who calls them, or drop them."
                ),
                source=self.name,
            )
        ]

    @staticmethod
    def _summary(gaps: int, total: int) -> str:
        if total == 0:
            return "No rubric configured for this problem."
        if gaps == 0:
            return "Every required concept for this problem appears in your design."
        return "{} required concept{} missing from your design.".format(
            gaps, "" if gaps == 1 else "s"
        )
