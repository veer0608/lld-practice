"""Turning what the browser posts into a `Submission`.

The design editor is a plain textarea with one class per line:

    ParkingLot: owns floors and answers availability | park, is_full | Floor, Ticket
    ^ name       ^ responsibility                      ^ methods       ^ collaborators

A line-based format rather than a JavaScript grid because the responsibility is
the field that matters, and a learner types it faster than they click it. The
parser is here, in the web layer, not in the domain: `DesignSubmission` should
never learn what a form looks like.
"""

from __future__ import annotations

from app.domain.errors import InvalidSubmission
from app.domain.submission import (
    ClassSpec,
    CodeSubmission,
    DesignSubmission,
    Submission,
    TextSubmission,
)


def parse_design_text(raw: str) -> list[ClassSpec]:
    """Parse the line format. Blank lines and `#` comments are skipped."""
    classes: list[ClassSpec] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise InvalidSubmission(
                "Line {}: expected 'ClassName: responsibility'. Got: {}".format(
                    lineno, line[:60]
                )
            )
        name, rest = line.split(":", 1)
        parts = [p.strip() for p in rest.split("|")]
        responsibility = parts[0] if parts else ""
        methods = _csv(parts[1]) if len(parts) > 1 else ()
        collaborators = _csv(parts[2]) if len(parts) > 2 else ()
        classes.append(
            ClassSpec(
                name=name.strip(),
                responsibility=responsibility,
                methods=methods,
                collaborators=collaborators,
            )
        )
    return classes


def _csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def build_submission(
    kind: str,
    design: str = "",
    trade_offs: str = "",
    notes: str = "",
    text: str = "",
    code: str = "",
) -> Submission:
    """Dispatch on the chosen format.

    The one place in the app that maps a form field to a submission type. A new
    format adds a branch here and a subclass there, and nothing else moves.
    """
    if kind == "design":
        return DesignSubmission(
            classes=parse_design_text(design),
            trade_offs=trade_offs.strip(),
            notes=notes.strip(),
        )
    if kind == "code":
        return CodeSubmission(source=code)
    if kind == "text":
        return TextSubmission(text=text)
    raise InvalidSubmission("Unknown submission format: " + repr(kind))
