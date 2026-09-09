"""Seed one weak attempt and one strong one, so the loop is visible in one command.

    python scripts/demo.py

The product's claim is that attempt 3 is better than attempt 1, and until now a
reviewer could only see that by hand-writing two designs before the progress
sparkline had anything to draw. This writes both, evaluates them, and prints where
to look.

Rubric-only by default. `build_evaluator` treats the model as optional, so the
scores here are deterministic, need no API key and touch no network, which is what
makes this safe to run before a demo rather than during one. Pass --llm to include
the model evaluator if a key is configured.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_LEARNER, Settings, build_service  # noqa: E402
from app.services.runner import InlineRunner  # noqa: E402
from app.web.forms import build_submission  # noqa: E402

PROBLEM = "parking-lot"

# Two classes, no collaborators worth the name, and a trade-off that does not name
# what was given up. Weak on purpose and weak in the ways the rubric measures.
WEAK = {
    "design": "\n".join(
        [
            "ParkingLot: manages the parking lot | park, unpark | Floor",
            "Floor: a floor of the lot | get_spot | ParkingSpot",
            "ParkingSpot: a spot | occupy |",
            "Car: a car that parks | drive |",
        ]
    ),
    "trade_offs": "Kept it simple.",
}

# The same problem taken seriously: responsibilities that do not overlap, real
# collaborators, and a trade-off that names the cost.
STRONG = {
    "design": "\n".join(
        [
            "ParkingLot: owns floors and answers availability | is_full, park_vehicle | Floor, SpotAllocator",
            "Floor: holds the parking spots on one level | find_free_spot | ParkingSpot",
            "ParkingSpot: one bay of a given size | occupy, release | Vehicle",
            "SpotAllocator: chooses which free spot a vehicle gets | allocate | Floor, ParkingSpot",
            "Ticket: links vehicle, spot and entry time | issued_at, close | ParkingSpot, Vehicle",
            "PricingStrategy: computes the fee from duration | fee_for | Ticket",
            "Vehicle: the thing being parked and its size | size |",
        ]
    ),
    "trade_offs": (
        "Chose one central SpotAllocator over per-floor allocators: easier to reason "
        "about and to change the allocation policy in one place, but it is a single "
        "point of contention under load and a floor cannot allocate independently."
    ),
}


def seed(service, label: str, payload: dict) -> int | None:
    submission = build_submission("design", **payload)
    submission.validate()
    # The learner the web UI reads. Seeding under any other id runs cleanly and
    # shows nothing, which is the one way this script could fail at its whole job.
    attempt = service.start_attempt(DEFAULT_LEARNER, PROBLEM)
    service.submit(attempt.id, submission)
    done = service.get_attempt(attempt.id)
    print(f"  {label:<8} attempt {done.id}  score {done.score_percent}")
    return done.score_percent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="also run the model evaluator; needs a key, and makes the scores vary",
    )
    args = parser.parse_args(argv)

    # InlineRunner rather than ThreadRunner: the script should not exit while an
    # evaluation is still running on a background thread.
    service = build_service(Settings(use_llm=args.llm), runner=InlineRunner())

    print(f"seeding two attempts on {PROBLEM}:")
    first = seed(service, "weak", WEAK)
    second = seed(service, "strong", STRONG)

    print()
    if first is not None and second is not None:
        print(f"progress: {first}% -> {second}%")
    print("open http://127.0.0.1:8000/problems/" + PROBLEM + " to see the sparkline,")
    print("or http://127.0.0.1:8000/history for both attempts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
