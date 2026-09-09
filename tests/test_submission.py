"""Submission formats: tokenising, validation, round-tripping."""

from __future__ import annotations

import pytest

from app.domain.errors import InvalidSubmission
from app.domain.submission import (
    ClassSpec,
    CodeSubmission,
    DesignSubmission,
    Submission,
    TextSubmission,
    split_words,
)


def test_camel_case_is_split_as_well_as_kept_whole():
    # The bug this pins: lowercasing before splitting means PricingStrategy
    # never matches the rubric keyword "pricing strategy".
    words = split_words("PricingStrategy find_free_spot")
    assert {"pricing", "strategy", "pricingstrategy", "find", "free", "spot"} <= words


def test_design_round_trips_through_serialisation(good_design):
    restored = Submission.deserialise(good_design.serialise())
    assert isinstance(restored, DesignSubmission)
    assert restored.render_for_evaluation() == good_design.render_for_evaluation()
    assert restored.trade_offs == good_design.trade_offs


def test_unknown_format_is_rejected_not_guessed():
    with pytest.raises(InvalidSubmission):
        Submission.deserialise('{"kind": "uml-diagram", "payload": {}}')


def test_design_without_responsibilities_is_rejected_and_names_the_classes():
    submission = DesignSubmission(
        classes=[ClassSpec("ParkingLot", "owns floors"), ClassSpec("Ticket", "")]
    )
    with pytest.raises(InvalidSubmission) as exc:
        submission.validate()
    assert "Ticket" in str(exc.value)


def test_design_with_no_classes_is_rejected():
    with pytest.raises(InvalidSubmission):
        DesignSubmission(classes=[]).validate()


def test_too_short_a_submission_is_rejected():
    with pytest.raises(InvalidSubmission):
        TextSubmission(text="a parking lot has spots").validate()


def test_code_symbols_come_from_the_ast_not_from_comments():
    submission = CodeSubmission(
        source=(
            "# this comment mentions PricingStrategy but nothing implements it\n"
            "class ParkingLot:\n"
            "    def park(self, vehicle):\n"
            "        return self.allocator.assign(vehicle)\n"
        )
    )
    symbols = submission.symbols()
    assert "parkinglot" in symbols
    assert "allocator" in symbols
    # The comment is not code, so it must not satisfy a rubric criterion.
    assert "pricingstrategy" not in symbols


def test_unparseable_code_falls_back_to_words_rather_than_failing():
    submission = CodeSubmission(source="class ParkingLot(:\n    def park(")
    assert submission.parse_error() is not None
    assert "parkinglot" in submission.symbols()


def test_acronyms_are_kept_as_words_when_splitting_identifiers():
    words = split_words("APIKey HTTPServer")
    assert {"api", "key", "apikey", "http", "server", "httpserver"} <= words
    assert not {"a", "i", "h", "t", "p"} & words


# -- structural notes belong to the format, not to the evaluator --------------


def test_a_new_format_gets_its_structural_notes_with_no_evaluator_change():
    """The extensibility claim, as a test rather than a sentence in a doc.

    This used to be false and silently so: RubricEvaluator switched on the three
    known subclasses, and a fourth registered fine, then received no structural
    checks at all with nothing to signal it.
    """
    from app.content.problems import PARKING_LOT
    from app.domain.feedback import FeedbackItem, Severity
    from app.domain.problem import Dimension
    from app.evaluation.rubric_evaluator import RubricEvaluator

    class DiagramSubmission(Submission):
        kind = "diagram-test"

        def __init__(self, src: str) -> None:
            self.src = src

        def render_for_evaluation(self) -> str:
            return self.src

        def symbols(self):
            return split_words(self.src)

        def to_payload(self):
            return {"src": self.src}

        @classmethod
        def from_payload(cls, payload):
            return cls(payload["src"])

        def structural_notes(self):
            if "-->" in self.src:
                return []
            return [
                FeedbackItem(
                    dimension=Dimension.RELATIONSHIPS,
                    severity=Severity.GAP,
                    message="No arrows in your diagram, so no relationships are stated.",
                )
            ]

    result = RubricEvaluator().evaluate(PARKING_LOT, DiagramSubmission("ParkingLot Floor " * 20))
    notes = [i for i in result.items if i.criterion_id is None]
    assert [n.message for n in notes] == [
        "No arrows in your diagram, so no relationships are stated."
    ]
    # The evaluator that surfaced it stamps its own name, so a learner can tell
    # who is making the claim.
    assert notes[0].source == "rubric"


def test_a_format_with_nothing_to_check_returns_no_notes():
    assert TextSubmission(text="x").structural_notes()  # prose always warns
    assert CodeSubmission(source="class A:\n    pass\n").structural_notes() == []
