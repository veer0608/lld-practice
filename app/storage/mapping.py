"""Turning domain objects into rows and back.

Deliberately its own module. If `Evaluation.to_json` lived on the dataclass,
the domain would own a storage format and every schema change would touch the
domain. Here, the mapping is one file that both storage backends share.
"""

from __future__ import annotations

import json
from datetime import datetime

from app.domain.feedback import DimensionScore, Evaluation, FeedbackItem, Severity
from app.domain.problem import Dimension


def evaluation_to_json(evaluation: Evaluation | None) -> str | None:
    if evaluation is None:
        return None
    return json.dumps(
        {
            "items": [
                {
                    "dimension": i.dimension.value,
                    "severity": i.severity.value,
                    "message": i.message,
                    "evidence": i.evidence,
                    "source": i.source,
                    "criterion_id": i.criterion_id,
                }
                for i in evaluation.items
            ],
            "scores": [
                {
                    "dimension": s.dimension.value,
                    "score": s.score,
                    "met": s.met,
                    "total": s.total,
                }
                for s in evaluation.scores
            ],
            "summary": evaluation.summary,
            "sources": evaluation.sources,
            "degraded": evaluation.degraded,
            "degraded_reason": evaluation.degraded_reason,
            "duration_ms": evaluation.duration_ms,
        }
    )


def evaluation_from_json(raw: str | None) -> Evaluation | None:
    if not raw:
        return None
    data = json.loads(raw)
    return Evaluation(
        items=[
            FeedbackItem(
                dimension=Dimension(i["dimension"]),
                severity=Severity(i["severity"]),
                message=i["message"],
                evidence=i.get("evidence", ""),
                source=i.get("source", "unknown"),
                criterion_id=i.get("criterion_id"),
            )
            for i in data.get("items", [])
        ],
        scores=[
            DimensionScore(
                dimension=Dimension(s["dimension"]),
                score=s["score"],
                met=s.get("met", 0),
                total=s.get("total", 0),
            )
            for s in data.get("scores", [])
        ],
        summary=data.get("summary", ""),
        sources=data.get("sources", []),
        degraded=data.get("degraded", False),
        degraded_reason=data.get("degraded_reason", ""),
        duration_ms=data.get("duration_ms", 0),
    )


def iso(moment: datetime) -> str:
    return moment.isoformat()


def parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw)
