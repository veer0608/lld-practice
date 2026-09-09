from __future__ import annotations

import pytest

from app.content.problems import PARKING_LOT, default_problem_repository
from app.domain.submission import ClassSpec, DesignSubmission
from app.evaluation.pipeline import EvaluationPipeline
from app.evaluation.rubric_evaluator import RubricEvaluator
from app.services.practice import PracticeService
from app.services.runner import InlineRunner
from app.storage.memory_store import InMemoryAttemptRepository


@pytest.fixture
def problem():
    return PARKING_LOT


@pytest.fixture
def good_design() -> DesignSubmission:
    """A design that covers most of the parking lot rubric."""
    return DesignSubmission(
        classes=[
            ClassSpec("ParkingLot", "Owns floors and answers availability",
                      ("is_full", "park_vehicle"), ("Floor", "SpotAllocator")),
            ClassSpec("Floor", "Holds the parking spots on one level",
                      ("find_free_spot",), ("ParkingSpot",)),
            ClassSpec("ParkingSpot", "One bay of a given size",
                      ("occupy", "release"), ("Vehicle",)),
            ClassSpec("Ticket", "Links vehicle, spot and entry time",
                      ("issued_at",), ("ParkingSpot",)),
            ClassSpec("PricingStrategy", "Computes the fee from duration",
                      ("fee_for",), ("Ticket",)),
            ClassSpec("Payment", "Takes money against a ticket",
                      ("settle",), ("Ticket", "PricingStrategy")),
        ],
        trade_offs="One central allocator rather than per-floor allocators: "
                   "simpler to reason about, but a single point of contention.",
    )


@pytest.fixture
def thin_design() -> DesignSubmission:
    """One class doing everything, no trade-off stated."""
    return DesignSubmission(
        classes=[
            ClassSpec("ParkingLot", "Does the parking, the pricing and the payment",
                      ("park", "unpark", "calculate_fee", "take_payment", "is_full")),
            ClassSpec("Vehicle", "A car that arrives"),
            ClassSpec("Logger", "Writes lines to a file"),
        ],
    )


def build_service(evaluator=None, runner=None) -> PracticeService:
    return PracticeService(
        problems=default_problem_repository(),
        attempts=InMemoryAttemptRepository(),
        evaluator=evaluator or EvaluationPipeline(required=[RubricEvaluator()]),
        runner=runner or InlineRunner(),
    )


@pytest.fixture
def service() -> PracticeService:
    return build_service()
