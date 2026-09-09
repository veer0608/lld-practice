"""The shape of feedback.

There is usually more than one valid LLD solution, so the platform never says
"correct" or "wrong". It says three things instead, and every one of them is
attributable:

* an observation tagged with a `Dimension` and a `Severity`,
* the `evidence` it is based on - the learner's own words or symbols,
* the `source` that produced it - which evaluator, so a learner can tell a
  mechanical check from a model's opinion.

That last field is the reason feedback from a deterministic checker and from
an LLM can sit in the same list without either one pretending to be the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .problem import Dimension


class Severity(str, Enum):
    STRENGTH = "strength"
    SUGGESTION = "suggestion"
    GAP = "gap"

    @property
    def rank(self) -> int:
        return {Severity.GAP: 0, Severity.SUGGESTION: 1, Severity.STRENGTH: 2}[self]


@dataclass(frozen=True)
class FeedbackItem:
    dimension: Dimension
    severity: Severity
    message: str
    evidence: str = ""
    source: str = "unknown"
    criterion_id: str | None = None


@dataclass(frozen=True)
class DimensionScore:
    """A 0..1 score on one axis, with the count it was derived from."""

    dimension: Dimension
    score: float
    met: int = 0
    total: int = 0

    @property
    def percent(self) -> int:
        return round(self.score * 100)


@dataclass
class Evaluation:
    """The result of running one or more evaluators over one submission."""

    items: list[FeedbackItem] = field(default_factory=list)
    scores: list[DimensionScore] = field(default_factory=list)
    summary: str = ""
    sources: list[str] = field(default_factory=list)
    degraded: bool = False
    degraded_reason: str = ""
    duration_ms: int = 0

    @property
    def overall(self) -> float:
        """Unweighted mean of dimension scores.

        Unweighted on purpose: weighting one LLD axis above another is a
        product claim we have not earned yet, and a hidden weight makes a
        score harder to argue with. See DESIGN.md.
        """
        if not self.scores:
            return 0.0
        return sum(s.score for s in self.scores) / len(self.scores)

    @property
    def overall_percent(self) -> int:
        return round(self.overall * 100)

    def by_severity(self, severity: Severity) -> list[FeedbackItem]:
        return [i for i in self.items if i.severity is severity]

    def sorted_items(self) -> list[FeedbackItem]:
        """Gaps first, then suggestions, then strengths.

        A learner who reads one line should read the most actionable one.
        """
        return sorted(self.items, key=lambda i: (i.severity.rank, i.dimension.value))

    def merge(self, other: Evaluation) -> Evaluation:
        """Combine two evaluations into one.

        Scores for a dimension present in both are averaged. Items are
        concatenated, never deduplicated: two sources agreeing is information,
        not noise, and each keeps its own `source` label.
        """
        merged_scores: list[DimensionScore] = []
        mine = {s.dimension: s for s in self.scores}
        theirs = {s.dimension: s for s in other.scores}
        for dim in list(mine) + [d for d in theirs if d not in mine]:
            a, b = mine.get(dim), theirs.get(dim)
            if a and b:
                merged_scores.append(
                    DimensionScore(dim, (a.score + b.score) / 2, a.met + b.met, a.total + b.total)
                )
            else:
                merged_scores.append(a or b)  # type: ignore[arg-type]

        return Evaluation(
            items=self.items + other.items,
            scores=merged_scores,
            summary=other.summary or self.summary,
            sources=self.sources + other.sources,
            degraded=self.degraded or other.degraded,
            degraded_reason="; ".join(
                r for r in (self.degraded_reason, other.degraded_reason) if r
            ),
            duration_ms=self.duration_ms + other.duration_ms,
        )
