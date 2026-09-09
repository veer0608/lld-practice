"""The seed problem catalogue.

Problems are authored content, kept as data rather than code paths: nothing in
the platform branches on which problem is being attempted. Adding a fourth
problem is appending to `CATALOGUE`, and moving the catalogue to JSON or a CMS
later is a new `ProblemRepository`, not a change here.

Rubric keywords are written as *alternatives a reasonable design would use*,
not as the one right name. "spot", "slot" and "bay" all satisfy the same
criterion, because penalising vocabulary rather than design is the failure mode
that makes automated LLD feedback useless.
"""

from __future__ import annotations

from app.domain.problem import Dimension, MatchScope, Problem, RubricCriterion as C
from app.storage.memory_store import InMemoryProblemRepository

PARKING_LOT = Problem(
    id="parking-lot",
    title="Parking Lot",
    difficulty="starter",
    tags=("classic", "state", "pricing"),
    statement=(
        "Design the domain model for a multi-level parking lot. Vehicles arrive, are "
        "assigned a place to park, and pay on the way out. The lot has several floors, "
        "and spots come in sizes that suit different vehicle types.\n\n"
        "Model the classes, their responsibilities and how they collaborate. You do not "
        "need to write a working system, and you do not need a database."
    ),
    requirements=(
        "Several floors, each with a number of parking spots.",
        "Spots differ by size; a vehicle can only use a spot that fits it.",
        "A vehicle is issued a ticket on entry and pays on exit.",
        "The fee depends on how long the vehicle stayed.",
        "The lot must be able to say whether it is full, per floor and overall.",
        "Pricing rules will change later. Make that cheap.",
    ),
    rubric=(
        C(
            id="pl-spot",
            dimension=Dimension.REQUIREMENTS,
            description="a parking spot is modelled as its own thing, not an integer count",
            keywords=("parking spot", "spot", "slot", "bay", "space"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="pl-level",
            dimension=Dimension.REQUIREMENTS,
            description="floors or levels are represented",
            keywords=("floor", "level", "deck"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="pl-ticket",
            dimension=Dimension.REQUIREMENTS,
            description="a ticket links a vehicle to a spot and an entry time",
            keywords=("ticket", "receipt", "token"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="pl-vehicle-type",
            dimension=Dimension.ABSTRACTION,
            description="vehicle size or type drives which spots are usable",
            keywords=("vehicle type", "vehicle size", "spot type", "size", "motorcycle", "truck"),
            required=True,
        ),
        C(
            id="pl-pricing",
            dimension=Dimension.EXTENSIBILITY,
            description="pricing is a separate collaborator, so a new rule does not edit the lot",
            keywords=("pricing strategy", "fee strategy", "rate", "pricing", "fee calculator"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="pl-assignment",
            dimension=Dimension.RESPONSIBILITY,
            description="something owns the decision of which spot a vehicle gets",
            keywords=("allocator", "assignment", "assign", "spot finder", "allocation"),
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="pl-availability",
            dimension=Dimension.RELATIONSHIPS,
            description="availability is answerable without scanning every spot from outside",
            keywords=("available", "availability", "occupied", "free", "capacity"),
        ),
        C(
            id="pl-payment",
            dimension=Dimension.RELATIONSHIPS,
            description="payment is modelled, and is not the same object as pricing",
            keywords=("payment", "transaction", "invoice", "checkout"),
            scope=MatchScope.TYPE_NAME,
        ),
    ),
    reference_notes=(
        "The decision that separates a strong answer here is where the fee is computed. "
        "A `calculate_fee` method on ParkingLot works today and has to be reopened for "
        "every new rule."
    ),
)

ELEVATOR = Problem(
    id="elevator",
    title="Elevator Controller",
    difficulty="core",
    tags=("classic", "state machine", "scheduling"),
    statement=(
        "Design the domain model for a bank of elevators in one building. People press "
        "a call button on a floor, and buttons inside the car for a destination. The "
        "controller decides which car serves which request and in what order.\n\n"
        "Focus on responsibilities and state, not on the scheduling algorithm itself. "
        "You may say 'nearest car wins' and move on, as long as the design makes a "
        "different rule easy to drop in."
    ),
    requirements=(
        "Several cars serving the same set of floors.",
        "Two request kinds: a hall call with a direction, and a car call with a destination.",
        "A car has a state: idle, moving up, moving down, doors open.",
        "Requests are queued and served in some order.",
        "The selection rule will change later. Make that cheap.",
        "A car must not accept a request it physically cannot serve.",
    ),
    rubric=(
        C(
            id="el-request",
            dimension=Dimension.REQUIREMENTS,
            description="a request is a first-class object, distinct from a floor number",
            keywords=("request", "call", "hall call", "car call"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="el-direction",
            dimension=Dimension.REQUIREMENTS,
            description="direction is modelled, not inferred from arithmetic at the call site",
            keywords=("direction",),
            required=True,
        ),
        C(
            id="el-state",
            dimension=Dimension.ABSTRACTION,
            description="the car has an explicit state, not a pile of booleans",
            keywords=("state", "idle", "moving", "doors open", "status"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="el-scheduler",
            dimension=Dimension.EXTENSIBILITY,
            description="the selection rule lives behind its own interface",
            keywords=("scheduler", "dispatcher", "strategy", "selection policy", "policy"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="el-controller",
            dimension=Dimension.RESPONSIBILITY,
            description="a controller coordinates cars rather than a car knowing about its siblings",
            keywords=("controller", "coordinator", "dispatcher", "bank"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="el-queue",
            dimension=Dimension.RELATIONSHIPS,
            description="each car owns its own pending stops",
            keywords=("queue", "pending", "stops", "schedule"),
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="el-door",
            dimension=Dimension.RELATIONSHIPS,
            description="doors are modelled, because they gate movement",
            keywords=("door", "doors"),
        ),
    ),
    reference_notes=(
        "The common miss is a single Elevator class that both moves itself and chooses "
        "which requests to take, which makes any new dispatch rule a rewrite."
    ),
)

VENDING_MACHINE = Problem(
    id="vending-machine",
    title="Vending Machine",
    difficulty="starter",
    tags=("classic", "state machine", "payments"),
    statement=(
        "Design the domain model for a vending machine. A customer selects an item, "
        "inserts money, and receives the item plus change. The machine tracks its own "
        "stock and its own cash.\n\n"
        "The interesting part is the state: what may legally happen in which order, and "
        "what happens when it cannot complete."
    ),
    requirements=(
        "Items live in slots, each with a price and a quantity.",
        "Money goes in as discrete coins or notes.",
        "The machine dispenses the item and the correct change.",
        "A selection is refused if the item is out of stock.",
        "A purchase is refused, and money refunded, if exact change cannot be made.",
        "A customer can cancel before dispensing and get their money back.",
    ),
    rubric=(
        C(
            id="vm-slot",
            dimension=Dimension.REQUIREMENTS,
            description="inventory is modelled per slot, with price and quantity",
            keywords=("slot", "inventory", "stock", "tray"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="vm-state",
            dimension=Dimension.ABSTRACTION,
            description="the machine has explicit states rather than flags",
            keywords=("state", "idle", "awaiting payment", "dispensing", "state machine"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="vm-money",
            dimension=Dimension.REQUIREMENTS,
            description="money is a domain type, not a float",
            keywords=("coin", "money", "denomination", "note", "cash"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="vm-change",
            dimension=Dimension.RESPONSIBILITY,
            description="making change is its own responsibility, not machine code inline",
            keywords=("change", "coin dispenser", "refund", "change maker"),
            required=True,
            scope=MatchScope.TYPE_NAME,
        ),
        C(
            id="vm-cancel",
            dimension=Dimension.REQUIREMENTS,
            description="cancellation and refund are represented",
            keywords=("cancel", "refund", "abort", "return money"),
        ),
        C(
            id="vm-transaction",
            dimension=Dimension.RELATIONSHIPS,
            description="a transaction ties selection, payment and dispensing together",
            keywords=("transaction", "purchase", "session", "order"),
            scope=MatchScope.TYPE_NAME,
        ),
    ),
    reference_notes=(
        "Strong answers make the illegal orderings impossible to express. Weak ones "
        "check a boolean at the top of every method."
    ),
)

CATALOGUE = (PARKING_LOT, ELEVATOR, VENDING_MACHINE)


def default_problem_repository() -> InMemoryProblemRepository:
    return InMemoryProblemRepository(list(CATALOGUE))
