"""The problem a learner practises against.

A Problem carries three separable things:

* the prose a learner reads (statement, requirements),
* the machine-checkable expectations (`RubricCriterion`), and
* the vocabulary the deterministic checker looks for (`expected_concepts`).

Keeping the rubric on the Problem rather than inside an evaluator is what
lets a second evaluation strategy be added later without touching either the
problems or the attempt lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Dimension(str, Enum):
    """The axes an LLD design is judged on.

    Deliberately small. Every criterion and every piece of feedback is tagged
    with one of these, which is what makes deterministic and LLM feedback
    mergeable: they speak the same vocabulary.
    """

    REQUIREMENTS = "requirements"
    ABSTRACTION = "abstraction"
    RESPONSIBILITY = "responsibility"
    RELATIONSHIPS = "relationships"
    EXTENSIBILITY = "extensibility"
    TRADE_OFFS = "trade_offs"

    @property
    def label(self) -> str:
        return {
            Dimension.REQUIREMENTS: "Requirements covered",
            Dimension.ABSTRACTION: "Abstractions chosen",
            Dimension.RESPONSIBILITY: "Responsibility placement",
            Dimension.RELATIONSHIPS: "Relationships and collaboration",
            Dimension.EXTENSIBILITY: "Extensibility",
            Dimension.TRADE_OFFS: "Trade-offs made explicit",
        }[self]


class MatchScope(str, Enum):
    """Where a criterion's keywords are allowed to match.

    Two different questions hide behind "is this concept present", and
    conflating them produced real false positives: a god class with a
    `get_change` method was credited with "making change is its own
    responsibility", and a design that said "opens the doors" was credited with
    "the car has an explicit state".

    ANYWHERE is for concepts a design may legitimately express in prose, in a
    method name, or in a responsibility. TYPE_NAME is for criteria that are
    claims about a type existing, which is a question only class and
    collaborator names can answer.
    """

    ANYWHERE = "anywhere"
    TYPE_NAME = "type_name"


@dataclass(frozen=True)
class RubricCriterion:
    """One checkable expectation.

    `keywords` are alternatives: any one of them satisfies the criterion. They
    are matched case-insensitively against the submission, in the scope the
    criterion asks for. This is crude on purpose; see DESIGN.md on why the
    crude signal is still worth having next to the LLM.
    """

    id: str
    dimension: Dimension
    description: str
    keywords: tuple[str, ...] = ()
    weight: float = 1.0
    required: bool = False
    scope: MatchScope = MatchScope.ANYWHERE


@dataclass(frozen=True)
class Problem:
    id: str
    title: str
    difficulty: str
    statement: str
    requirements: tuple[str, ...]
    rubric: tuple[RubricCriterion, ...]
    tags: tuple[str, ...] = field(default_factory=tuple)

    def criterion(self, criterion_id: str) -> RubricCriterion:
        for c in self.rubric:
            if c.id == criterion_id:
                return c
        raise KeyError(criterion_id)

    @property
    def dimensions(self) -> tuple[Dimension, ...]:
        seen: list[Dimension] = []
        for c in self.rubric:
            if c.dimension not in seen:
                seen.append(c.dimension)
        return tuple(seen)
