"""The HTTP edge.

Thin on purpose. Routes read the form, call one service method, and render.
There is no domain logic here: the two things this layer owns are translating
`DomainError` into status codes and deciding what a page shows.

The learner is a fixed demo id. Auth is out of scope for a 2-day prototype and
faking it would add surface without adding evidence of design skill; every
service call already takes `learner_id`, so a real session drops in at this
layer alone.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import DEFAULT_LEARNER, Settings, build_service
from app.domain.attempt import Attempt, AttemptStatus
from app.domain.errors import DomainError, IllegalTransition, InvalidSubmission, NotFound
from app.services.practice import PracticeService

from .forms import build_submission

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def attempt_json(attempt: Attempt) -> dict:
    evaluation = attempt.evaluation
    return {
        "id": attempt.id,
        "problem_id": attempt.problem_id,
        "attempt_no": attempt.attempt_no,
        "status": attempt.status.value,
        "error": attempt.error,
        "score": attempt.score_percent,
        "evaluation": None
        if evaluation is None
        else {
            "summary": evaluation.summary,
            "trend": evaluation.trend_percent,
            "comparable": evaluation.comparable_percent,
            "merged": evaluation.overall_percent,
            "contributions": [
                {"source": c.source, "percent": c.percent, "reproducible": c.reproducible}
                for c in evaluation.contributions
            ],
            "degraded": evaluation.degraded,
            "degraded_reason": evaluation.degraded_reason,
            "sources": evaluation.sources,
            "scores": [
                {"dimension": s.dimension.value, "percent": s.percent}
                for s in evaluation.scores
            ],
            "items": [
                {
                    "dimension": i.dimension.value,
                    "severity": i.severity.value,
                    "message": i.message,
                    "evidence": i.evidence,
                    "source": i.source,
                }
                for i in evaluation.sorted_items()
            ],
        },
    }


def create_app(service: PracticeService | None = None, settings: Settings | None = None) -> FastAPI:
    """Build the app around an injected service.

    Tests pass an in-memory service with an inline runner, so the whole HTTP
    surface is exercised with no database, no threads and no network.
    """
    app = FastAPI(title="LLD Practice Platform")
    app.state.service = service or build_service(settings)
    app.include_router(_router())

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        status = {NotFound: 404, InvalidSubmission: 400, IllegalTransition: 409}.get(
            type(exc), 400
        )
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": str(exc)}, status_code=status)
        return TEMPLATES.TemplateResponse(
            request, "error.html", {"message": str(exc), "status": status}, status_code=status
        )

    return app


def _service(request: Request) -> PracticeService:
    return request.app.state.service


def _router() -> APIRouter:
    router = APIRouter()

    # -- pages --------------------------------------------------------

    @router.get("/", response_class=HTMLResponse)
    def index(request: Request):
        service = _service(request)
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "problems": service.list_problems(),
                "attempts": service.history(DEFAULT_LEARNER)[:5],
            },
        )

    @router.get("/problems/{problem_id}", response_class=HTMLResponse)
    def problem_page(request: Request, problem_id: str):
        service = _service(request)
        problem = service.get_problem(problem_id)
        return TEMPLATES.TemplateResponse(
            request,
            "problem.html",
            {
                "problem": problem,
                "history": service.history(DEFAULT_LEARNER, problem_id),
                "progress": service.progress(DEFAULT_LEARNER, problem_id),
                "error": None,
                "kind": "design",
                "submitted": {},
            },
        )

    @router.post("/problems/{problem_id}/submit")
    def submit(
        request: Request,
        problem_id: str,
        kind: str = Form("design"),
        design: str = Form(""),
        trade_offs: str = Form(""),
        notes: str = Form(""),
        text: str = Form(""),
        code: str = Form(""),
    ):
        service = _service(request)
        submitted = {
            "design": design,
            "trade_offs": trade_offs,
            "notes": notes,
            "text": text,
            "code": code,
        }
        try:
            # Parsing has to sit inside the guard too. A mistyped design line
            # raises from build_submission, not from validate(), and that is the
            # likeliest way a learner reaches this path at all.
            submission = build_submission(kind, **submitted)
            submission.validate()
        except InvalidSubmission as exc:
            # Back to the form with the work still in it. The generic error page
            # loses everything the learner typed, and mistyping one line of the
            # design format is the most likely way to reach here, so the page that
            # punishes a typo by discarding the design is the one place this
            # product's own practice loop breaks.
            return TEMPLATES.TemplateResponse(
                request,
                "problem.html",
                {
                    "problem": service.get_problem(problem_id),
                    "history": service.history(DEFAULT_LEARNER, problem_id),
                    "progress": service.progress(DEFAULT_LEARNER, problem_id),
                    "error": str(exc),
                    "kind": kind,
                    "submitted": submitted,
                },
                status_code=400,
            )
        attempt = service.start_attempt(DEFAULT_LEARNER, problem_id)
        service.submit(attempt.id, submission)
        return RedirectResponse("/attempts/" + attempt.id, status_code=303)

    @router.get("/attempts/{attempt_id}", response_class=HTMLResponse)
    def attempt_page(request: Request, attempt_id: str):
        service = _service(request)
        attempt = service.get_attempt(attempt_id)
        return TEMPLATES.TemplateResponse(
            request,
            "attempt.html",
            {
                "attempt": attempt,
                "problem": service.get_problem(attempt.problem_id),
                "progress": service.progress(DEFAULT_LEARNER, attempt.problem_id),
                "pending": attempt.is_pending,
            },
        )

    @router.post("/attempts/{attempt_id}/retry")
    def retry(request: Request, attempt_id: str):
        service = _service(request)
        attempt = service.get_attempt(attempt_id)
        # FAILED is not in this tuple, so it is already covered. This used to be an
        # if/elif with identical bodies whose first branch could never change the
        # outcome of the second.
        if attempt.status not in (AttemptStatus.EVALUATING, AttemptStatus.EVALUATED):
            service.retry_evaluation(attempt_id)
        return RedirectResponse("/attempts/" + attempt_id, status_code=303)

    @router.get("/history", response_class=HTMLResponse)
    def history_page(request: Request):
        service = _service(request)
        return TEMPLATES.TemplateResponse(
            request,
            "history.html",
            {"attempts": service.history(DEFAULT_LEARNER)},
        )

    # -- json ---------------------------------------------------------

    @router.get("/api/problems")
    def api_problems(request: Request):
        return [
            {
                "id": p.id,
                "title": p.title,
                "difficulty": p.difficulty,
                "requirements": list(p.requirements),
            }
            for p in _service(request).list_problems()
        ]

    @router.get("/api/attempts/{attempt_id}")
    def api_attempt(request: Request, attempt_id: str):
        return attempt_json(_service(request).get_attempt(attempt_id))

    @router.get("/api/attempts")
    def api_history(request: Request, problem_id: str | None = None):
        return [
            attempt_json(a)
            for a in _service(request).history(DEFAULT_LEARNER, problem_id)
        ]

    @router.get("/healthz")
    def healthz(request: Request):
        service = _service(request)
        evaluator = service.evaluator
        return {
            "ok": True,
            "problems": len(service.list_problems()),
            "evaluators": {
                "required": [e.name for e in getattr(evaluator, "required", [])],
                "optional": [e.name for e in getattr(evaluator, "optional", [])],
            },
        }

    return router
