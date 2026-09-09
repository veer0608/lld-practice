"""Entry point.

    python -m uvicorn main:app --reload --port 8000

Kept separate from `app.web.api` so importing the web module does not build a
database connection or a thread pool. Tests import `create_app` and pass their
own service.
"""

from __future__ import annotations

from app.config import DEFAULT_LEARNER, Settings, build_service
from app.web.api import create_app

settings = Settings()
service = build_service(settings)

# Anything left mid-evaluation by a restart gets picked back up. See
# PracticeService.resume_pending for why this exists at all.
service.resume_pending(DEFAULT_LEARNER)

app = create_app(service)
