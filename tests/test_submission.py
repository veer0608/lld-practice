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
