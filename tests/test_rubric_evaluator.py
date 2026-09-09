"""The deterministic evaluator. Same input, same output, no network."""

from __future__ import annotations

from app.domain.feedback import Severity
from app.domain.problem import Dimension
from app.domain.submission import ClassSpec, CodeSubmission, DesignSubmission, TextSubmission
from app.evaluation.rubric_evaluator import RubricEvaluator


def evaluate(problem, submission):
    return RubricEvaluator().evaluate(problem, submission)


def test_a_covering_design_scores_well_and_cites_evidence(problem, good_design):
    result = evaluate(problem, good_design)
    assert result.overall > 0.8
    strengths = result.by_severity(Severity.STRENGTH)
    assert strengths
    assert all(item.evidence for item in strengths)
    assert all(item.source == "rubric" for item in result.items)


def test_a_missing_required_concept_is_a_gap_not_a_suggestion(problem, good_design):
    without_pricing = DesignSubmission(
        classes=[
            ClassSpec(
                c.name,
                c.responsibility,
                c.methods,
                tuple(x for x in c.collaborators if x != "PricingStrategy"),
            )
            for c in good_design.classes
            if c.name != "PricingStrategy"
        ],
        trade_offs=good_design.trade_offs,
    )
    result = evaluate(problem, without_pricing)
    gaps = {i.criterion_id for i in result.by_severity(Severity.GAP)}
    assert "pl-pricing" in gaps


def test_evaluation_is_deterministic(problem, good_design):
    first, second = evaluate(problem, good_design), evaluate(problem, good_design)
    assert [i.message for i in first.sorted_items()] == [i.message for i in second.sorted_items()]
    assert first.overall == second.overall


def test_multi_word_keywords_need_every_word(problem):
    # "parking" alone must not satisfy the "parking spot" criterion, or the
    # checker rewards vocabulary rather than modelling.
    submission = DesignSubmission(
        classes=[ClassSpec("Parking", "handles all the parking things", ("park",))],
        trade_offs="none",
        notes="x" * 150,
    )
    result = evaluate(problem, submission)
    spot = next(i for i in result.items if i.criterion_id == "pl-spot")
    assert spot.severity is Severity.GAP


def test_a_missing_trade_off_is_reported(problem, thin_design):
    result = evaluate(problem, thin_design)
    trade_off_items = [i for i in result.items if i.dimension is Dimension.TRADE_OFFS]
    assert any(i.severity is Severity.GAP for i in trade_off_items)


def test_a_god_class_is_flagged_with_the_numbers(problem, thin_design):
    result = evaluate(problem, thin_design)
    god = next(i for i in result.items if "holds most of the behaviour" in i.message)
    assert "ParkingLot" in god.message
    assert "%" in god.evidence


def test_a_disconnected_class_is_flagged(problem, thin_design):
    result = evaluate(problem, thin_design)
    orphans = next(i for i in result.items if "not connected to anything" in i.message)
    assert "Logger" in orphans.message


def test_unparseable_code_is_a_caveat_not_a_failure(problem):
    submission = CodeSubmission(
        source="class ParkingLot(:\n    def park(self): pass\n" + "# padding\n" * 20
    )
    result = evaluate(problem, submission)
    assert result.scores  # still scored
    assert any("did not parse" in i.message for i in result.items)


def test_prose_submissions_are_told_they_get_shallower_feedback(problem):
    result = evaluate(problem, TextSubmission(text="A parking lot has floors. " * 12))
    assert any("Prose submissions" in i.message for i in result.items)


# -- scope: "modelled as its own thing" is not "the word appears somewhere" ---
#
# All four cases below were real false positives found by running the Elevator
# and Vending Machine problems end to end. Each one credited a god class with
# having modelled a concept, on the strength of a method name.


def test_a_method_named_get_change_is_not_a_change_maker():
    from app.content.problems import VENDING_MACHINE

    god_class = DesignSubmission(
        classes=[
            ClassSpec("VendingMachine", "does the whole thing",
                      ("buy", "refill", "get_change", "check_money", "reset")),
            ClassSpec("Item", "a snack in the machine", ("price",)),
            ClassSpec("Screen", "shows text to the customer", ("show",)),
        ],
    )
    result = evaluate(VENDING_MACHINE, god_class)
    met = {i.criterion_id for i in result.by_severity(Severity.STRENGTH)}
    assert "vm-change" not in met
    assert "vm-money" not in met  # check_money is a method, not a Money type


def test_opening_the_doors_is_not_an_explicit_state_machine():
    from app.content.problems import ELEVATOR

    god_class = DesignSubmission(
        classes=[
            ClassSpec("Elevator", "goes up and down, picks requests and opens the doors",
                      ("move", "add_floor", "run", "choose_next", "open")),
            ClassSpec("Building", "has some elevators", ("get_elevator",)),
            ClassSpec("Person", "presses a button", ("press",)),
        ],
    )
    result = evaluate(ELEVATOR, god_class)
    met = {i.criterion_id for i in result.by_severity(Severity.STRENGTH)}
    assert "el-state" not in met
    assert "el-direction" not in met  # "goes up and down" is not modelling direction


def test_a_collaborator_still_counts_as_a_declared_type(problem, good_design):
    # Naming PricingStrategy as a collaborator asserts the type exists, even
    # without writing its own row. Tightening the scope must not break this.
    from app.domain.submission import ClassSpec as CS

    referenced_only = DesignSubmission(
        classes=[
            CS("ParkingLot", "owns floors and answers availability",
               ("is_full",), ("Floor", "PricingStrategy")),
            CS("Floor", "holds the spots on one level", ("find_free_spot",), ("ParkingSpot",)),
            CS("ParkingSpot", "one bay of a given size", ("occupy",), ("Vehicle",)),
        ],
        trade_offs="Pricing behind an interface.",
    )
    met = {
        i.criterion_id
        for i in evaluate(problem, referenced_only).by_severity(Severity.STRENGTH)
    }
    assert "pl-pricing" in met


def test_code_submissions_scope_to_class_definitions_not_method_names(problem):
    source = (
        "class ParkingLot:\n"
        "    def get_pricing(self):\n"
        "        return self.rate\n"
        "    def make_ticket(self):\n"
        "        pass\n"
    ) + "# padding to clear the length floor\n" * 8
    result = evaluate(problem, CodeSubmission(source=source))
    met = {i.criterion_id for i in result.by_severity(Severity.STRENGTH)}
    assert "pl-pricing" not in met
    assert "pl-ticket" not in met


def test_a_gap_on_a_type_criterion_says_a_class_is_missing(problem, thin_design):
    pricing = next(i for i in evaluate(problem, thin_design).items if i.criterion_id == "pl-pricing")
    assert pricing.evidence.startswith("no class named")


def test_summary_counts_only_missing_rubric_criteria(problem, thin_design):
    result = evaluate(problem, thin_design)
    required_gaps = [
        item
        for item in result.items
        if item.criterion_id is not None and item.severity is Severity.GAP
    ]
    assert result.summary == f"{len(required_gaps)} required concepts missing from your design."
