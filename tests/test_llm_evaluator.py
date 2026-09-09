"""The LLM evaluator, tested with a fake client.

No network in the suite. What is under test is our handling of what a model
sends back, which is the part that actually breaks: fenced JSON, prose around
the object, invented evidence, unknown dimension names, an empty response.
"""

from __future__ import annotations

import json

import pytest

from app.domain.feedback import Severity
from app.domain.problem import Dimension
from app.evaluation.evaluator import EvaluationError
from app.evaluation.llm_client import GeminiClient, LLMUnavailable
from app.evaluation.llm_evaluator import LLMEvaluator


class FakeClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    @property
    def configured(self) -> bool:
        return True

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class DeadClient(FakeClient):
    def complete(self, prompt: str) -> str:
        raise LLMUnavailable("gemini-3.1-flash-lite: daily quota exhausted")


def response(items, dimensions=None, summary="Move pricing off the lot."):
    return json.dumps(
        {
            "summary": summary,
            "dimensions": dimensions or [{"dimension": "abstraction", "score": 0.7}],
            "items": items,
        }
    )


def test_it_parses_a_fenced_json_response(problem, good_design):
    raw = "Here is my review:\n```json\n" + response(
        [
            {
                "dimension": "responsibility",
                "severity": "suggestion",
                "message": "PricingStrategy is right, but Payment reaches into it.",
                "evidence": "Payment: Takes money against a ticket",
            }
        ]
    ) + "\n```\nHope that helps."
    result = LLMEvaluator(FakeClient(raw)).evaluate(problem, good_design)
    assert len(result.items) == 1
    assert result.items[0].dimension is Dimension.RESPONSIBILITY
    assert result.items[0].source == "llm"


def test_observations_with_invented_evidence_are_withheld(problem, good_design):
    raw = response(
        [
            {
                "dimension": "abstraction",
                "severity": "gap",
                "message": "Your ElevatorController is doing too much.",
                "evidence": "ElevatorController dispatches cars and computes routes",
            },
            {
                "dimension": "relationships",
                "severity": "strength",
                "message": "Ticket links the vehicle to the spot cleanly.",
                "evidence": "Ticket: Links vehicle, spot and entry time",
            },
        ]
    )
    result = LLMEvaluator(FakeClient(raw)).evaluate(problem, good_design)
    messages = [i.message for i in result.items]
    assert "Ticket links the vehicle to the spot cleanly." in messages
    assert not any("ElevatorController" in m for m in messages)
    assert "withheld" in result.summary


def test_unknown_dimension_names_are_dropped(problem, good_design):
    raw = response(
        [
            {
                "dimension": "vibes",
                "severity": "gap",
                "message": "Not enough vibes.",
                "evidence": "ParkingLot: Owns floors and answers availability",
            }
        ]
    )
    result = LLMEvaluator(FakeClient(raw)).evaluate(problem, good_design)
    assert result.items == []


def test_an_unknown_severity_degrades_to_suggestion(problem, good_design):
    raw = response(
        [
            {
                "dimension": "abstraction",
                "severity": "catastrophic",
                "message": "Consider splitting Floor.",
                "evidence": "Floor: Holds the parking spots on one level",
            }
        ]
    )
    result = LLMEvaluator(FakeClient(raw)).evaluate(problem, good_design)
    assert result.items[0].severity is Severity.SUGGESTION


def test_a_response_with_no_json_is_a_retryable_error(problem, good_design):
    with pytest.raises(EvaluationError) as exc:
        LLMEvaluator(FakeClient("I could not review this.")).evaluate(problem, good_design)
    assert exc.value.retryable


def test_malformed_json_is_a_retryable_error(problem, good_design):
    with pytest.raises(EvaluationError):
        LLMEvaluator(FakeClient('{"summary": "x", "items": [},')).evaluate(problem, good_design)


def test_a_response_with_no_scores_is_rejected(problem, good_design):
    raw = json.dumps({"summary": "fine", "dimensions": [], "items": []})
    with pytest.raises(EvaluationError):
        LLMEvaluator(FakeClient(raw)).evaluate(problem, good_design)


def test_scores_are_clamped(problem, good_design):
    raw = response([], dimensions=[{"dimension": "abstraction", "score": 4.2}])
    result = LLMEvaluator(FakeClient(raw)).evaluate(problem, good_design)
    assert result.scores[0].score == 1.0


def test_a_dead_client_becomes_a_retryable_evaluation_error(problem, good_design):
    with pytest.raises(EvaluationError) as exc:
        LLMEvaluator(DeadClient("")).evaluate(problem, good_design)
    assert exc.value.retryable
    assert "quota" in str(exc.value)


def test_the_prompt_carries_the_problem_and_the_submission(problem, good_design):
    client = FakeClient(response([]))
    LLMEvaluator(client).evaluate(problem, good_design)
    prompt = client.prompts[0]
    assert problem.title in prompt
    assert "PricingStrategy" in prompt
    assert "{{" not in prompt  # every placeholder was filled


def test_the_client_is_unavailable_rather_than_crashing_without_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiClient(api_key=None)
    client.api_key = None  # simulate no .env either
    assert client.configured is False
    assert LLMEvaluator(client).is_available is False


def test_a_daily_quota_body_is_recognised_but_a_per_minute_one_is_not():
    # Same 429 status, opposite handling: one waits, the other moves on.
    daily = '{"error":{"details":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel"}]}}'
    burst = '{"error":{"details":[{"quotaId":"GenerateRequestsPerMinutePerProject"}]}}'
    assert GeminiClient._is_daily_wall(daily) is True
    assert GeminiClient._is_daily_wall(burst) is False
