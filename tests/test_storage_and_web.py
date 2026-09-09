"""Persistence round-trips and the HTTP surface."""

from __future__ import annotations

import pytest

NL = chr(10)
from fastapi.testclient import TestClient

from app.domain.attempt import AttemptStatus
from app.domain.errors import InvalidSubmission
from app.domain.submission import DesignSubmission
from app.storage.sqlite_store import SqliteAttemptRepository
from app.web.api import create_app
from app.web.forms import build_submission, parse_design_text

from .conftest import build_service


# -- storage ----------------------------------------------------------


@pytest.fixture
def sqlite_repo(tmp_path):
    repo = SqliteAttemptRepository(tmp_path / "test.db")
    yield repo
    repo.close()


def test_an_evaluated_attempt_survives_a_round_trip(sqlite_repo, service, good_design):
    service.attempts = sqlite_repo
    attempt = service.start_attempt("veer", "parking-lot")
    service.submit(attempt.id, good_design)

    reloaded = sqlite_repo.get(attempt.id)
    assert reloaded.status is AttemptStatus.EVALUATED
    assert isinstance(reloaded.submission, DesignSubmission)
    assert reloaded.submission.trade_offs == good_design.trade_offs
    assert reloaded.evaluation.overall == pytest.approx(
        service.get_attempt(attempt.id).evaluation.overall
    )
    assert reloaded.evaluation.items[0].source == "rubric"


def test_saving_the_same_attempt_twice_updates_rather_than_duplicates(
    sqlite_repo, service, good_design
):
    service.attempts = sqlite_repo
    attempt = service.start_attempt("veer", "parking-lot")
    service.submit(attempt.id, good_design)
    service.submit  # no-op, readability
    assert sqlite_repo.count_for("veer", "parking-lot") == 1


def test_a_new_repository_on_the_same_file_sees_the_data(tmp_path, good_design):
    path = tmp_path / "persist.db"
    first = SqliteAttemptRepository(path)
    service = build_service()
    service.attempts = first
    attempt = service.start_attempt("veer", "parking-lot")
    service.submit(attempt.id, good_design)
    first.close()

    second = SqliteAttemptRepository(path)
    assert second.get(attempt.id).score_percent is not None
    second.close()


# -- form parsing -----------------------------------------------------


def test_the_line_format_parses_names_responsibilities_methods_and_collaborators():
    classes = parse_design_text(
        "# a comment\n"
        "ParkingLot: owns floors | park, is_full | Floor, Ticket\n"
        "\n"
        "Ticket: links a vehicle to a spot\n"
    )
    assert [c.name for c in classes] == ["ParkingLot", "Ticket"]
    assert classes[0].methods == ("park", "is_full")
    assert classes[0].collaborators == ("Floor", "Ticket")
    assert classes[1].methods == ()


def test_a_line_without_a_responsibility_separator_says_which_line():
    with pytest.raises(InvalidSubmission) as exc:
        parse_design_text("ParkingLot owns floors")
    assert "Line 1" in str(exc.value)


def test_an_unknown_format_is_rejected():
    with pytest.raises(InvalidSubmission):
        build_submission("uml")


# -- http -------------------------------------------------------------


@pytest.fixture
def client():
    return TestClient(create_app(build_service()))


def test_the_problem_list_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Parking Lot" in response.text


def test_the_whole_loop_over_http(client):
    design = (
        "ParkingLot: owns floors and answers availability | is_full, park | Floor, SpotAllocator\n"
        "Floor: holds the parking spots on one level | find_free_spot | ParkingSpot\n"
        "ParkingSpot: one bay of a given size | occupy, release | Vehicle\n"
        "Ticket: links vehicle, spot and entry time | issued_at | ParkingSpot\n"
        "PricingStrategy: computes the fee from duration | fee_for | Ticket\n"
    )
    submit = client.post(
        "/problems/parking-lot/submit",
        data={"kind": "design", "design": design, "trade_offs": "One allocator, simpler but central."},
        follow_redirects=False,
    )
    assert submit.status_code == 303
    attempt_url = submit.headers["location"]

    page = client.get(attempt_url)
    assert page.status_code == 200
    assert "By dimension" in page.text

    status = client.get("/api" + attempt_url).json()
    assert status["status"] == "evaluated"
    assert status["score"] is not None
    assert status["evaluation"]["items"]

    history = client.get("/history")
    assert "#1" in history.text


def test_a_bad_design_line_returns_400_with_the_reason(client):
    response = client.post(
        "/problems/parking-lot/submit", data={"kind": "design", "design": "ParkingLot owns floors"}
    )
    assert response.status_code == 400
    assert "Line 1" in response.text


def test_a_rejected_submission_gives_the_work_back(client):
    """The practice loop's own failure mode.

    Mistyping one line of the design format is the likeliest way to be refused,
    and sending a bare error page for it means a learner loses everything they
    typed. The spec's Practice row is "a learner can start an attempt and work on
    a solution", which a page that discards the solution does not satisfy.
    """
    design = NL.join([
        "ParkingLot owns floors and answers availability",
        "Floor: holds the parking spots on one level | find_free_spot | ParkingSpot",
    ])
    trade_offs = "One central allocator: simpler, but a single point of contention."
    response = client.post(
        "/problems/parking-lot/submit",
        data={"kind": "design", "design": design, "trade_offs": trade_offs},
    )
    assert response.status_code == 400
    # The reason, on the form rather than on an error page.
    assert "Line 1" in response.text
    assert "Submit for feedback" in response.text
    # And every character of the work still there.
    assert "Floor: holds the parking spots on one level" in response.text
    assert trade_offs in response.text


def test_a_rejected_code_submission_comes_back_on_the_code_pane(client):
    response = client.post(
        "/problems/parking-lot/submit", data={"kind": "code", "code": "   "}
    )
    assert response.status_code == 400
    # The pane the learner was using is the one shown, not the design default.
    assert 'id="pane-code"' in response.text
    assert 'id="pane-code" hidden' not in response.text


def test_a_valid_submission_is_unaffected(client):
    design = NL.join([
        "ParkingLot: owns floors and answers availability | is_full, park | Floor",
        "Floor: holds the parking spots on one level | find_free_spot | ParkingSpot",
    ])
    response = client.post(
        "/problems/parking-lot/submit",
        data={"kind": "design", "design": design, "trade_offs": "Central allocator."},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_a_design_with_no_responsibilities_is_refused(client):
    response = client.post(
        "/problems/parking-lot/submit",
        data={"kind": "design", "design": "ParkingLot:\nTicket:\n"},
    )
    assert response.status_code == 400
    assert "responsibility" in response.text


def test_an_unknown_problem_is_a_404(client):
    assert client.get("/problems/nope").status_code == 404


def test_an_unknown_attempt_is_a_404_in_json_too(client):
    response = client.get("/api/attempts/nope")
    assert response.status_code == 404
    assert "error" in response.json()


def test_healthz_reports_which_evaluators_are_wired(client):
    body = client.get("/healthz").json()
    assert body["ok"] is True
    assert body["evaluators"]["required"] == ["rubric"]


def test_rejected_http_submissions_do_not_consume_attempt_numbers(client):
    design = (
        "ParkingLot: owns floors and answers availability | is_full, park | Floor, SpotAllocator\n"
        "Floor: holds the parking spots on one level | find_free_spot | ParkingSpot\n"
        "ParkingSpot: one bay of a given size | occupy, release | Vehicle\n"
        "Ticket: links vehicle, spot and entry time | issued_at | ParkingSpot\n"
        "PricingStrategy: computes the fee from duration | fee_for | Ticket\n"
    )
    payload = {"kind": "design", "design": design, "trade_offs": "A central allocator is simpler."}

    assert client.post("/problems/parking-lot/submit", data=payload, follow_redirects=False).status_code == 303
    for _ in range(3):
        assert client.post(
            "/problems/parking-lot/submit",
            data={"kind": "design", "design": "ParkingLot owns floors"},
        ).status_code == 400
    second = client.post("/problems/parking-lot/submit", data=payload, follow_redirects=False)

    assert second.status_code == 303
    assert client.get("/api" + second.headers["location"]).json()["attempt_no"] == 2
    assert [a["attempt_no"] for a in client.get("/api/attempts").json()] == [2, 1]


def test_a_mistyped_design_line_does_not_discard_the_learners_work(client):
    """The likeliest way to reach the error path must not cost the design.

    This raises from build_submission during parsing, not from validate(), so
    it only stays on the form if the guard wraps parsing as well.
    """
    response = client.post(
        "/problems/parking-lot/submit",
        data={
            "kind": "design",
            "design": "ParkingLot owns floors",
            "trade_offs": "one central allocator, simpler but contended",
        },
    )
    assert response.status_code == 400
    assert "Line 1" in response.text
    assert "ParkingLot owns floors" in response.text
    assert "one central allocator, simpler but contended" in response.text
