"""What a learner hands in.

The assignment asks what a learner must actually provide for an LLD attempt
to be meaningful. The answer this platform commits to: named classes with
stated responsibilities and stated collaborators, plus the trade-off the
learner knowingly made. Free prose is accepted but is explicitly the weakest
format, because almost nothing in it can be checked.

Three formats ship. Each is a `Submission` subclass that knows how to turn
itself into the two views every evaluator needs:

* `render_for_evaluation()` - a flat text view, for the LLM,
* `symbols()` - the identifiers the learner actually named, for the
  deterministic checker.

Adding a fourth format (a diagram DSL, a UML upload) means adding one subclass.
No evaluator changes, because evaluators depend on those two methods only.
"""

from __future__ import annotations

import ast
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from .errors import InvalidSubmission

MIN_TEXT_CHARS = 120


class Submission(ABC):
    """Base class for every submission format."""

    kind: ClassVar[str] = ""
    _registry: ClassVar[dict[str, type[Submission]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "kind", ""):
            Submission._registry[cls.kind] = cls

    @abstractmethod
    def render_for_evaluation(self) -> str:
        """A flat, human-readable view of the design."""

    @abstractmethod
    def symbols(self) -> set[str]:
        """Lowercased identifiers and words the learner used."""

    def declared_types(self) -> set[str]:
        """Lowercased tokens from the types the learner actually declared.

        A narrower haystack than `symbols`, for criteria that ask whether a
        concept was modelled as its own thing rather than merely mentioned.
        A method called `get_change` is not a ChangeMaker.

        The default is every symbol, which is the honest answer for a format
        that cannot tell a type from a verb. Prose falls back to it, and is one
        more reason prose is the weakest format here.
        """
        return self.symbols()

    @abstractmethod
    def to_payload(self) -> dict[str, Any]:
        """JSON-serialisable form, for storage."""

    @classmethod
    @abstractmethod
    def from_payload(cls, payload: dict[str, Any]) -> Submission:
        """Rebuild from `to_payload` output."""

    def validate(self) -> None:
        """Raise InvalidSubmission if this cannot be meaningfully evaluated.

        Cheap and local. Anything that needs the Problem to decide belongs in
        an evaluator, not here.
        """
        if len(self.render_for_evaluation().strip()) < MIN_TEXT_CHARS:
            raise InvalidSubmission(
                "Submission is too short to evaluate "
                f"(need at least {MIN_TEXT_CHARS} characters of design)."
            )

    def serialise(self) -> str:
        return json.dumps({"kind": self.kind, "payload": self.to_payload()})

    @staticmethod
    def deserialise(raw: str) -> Submission:
        data = json.loads(raw)
        kind = data["kind"]
        cls = Submission._registry.get(kind)
        if cls is None:
            raise InvalidSubmission("Unknown submission format: " + repr(kind))
        return cls.from_payload(data["payload"])

    @staticmethod
    def formats() -> tuple[str, ...]:
        return tuple(sorted(Submission._registry))


def split_words(text: str) -> set[str]:
    """Split identifiers and prose into comparable lowercase tokens.

    CamelCase and snake_case are broken apart as well as kept whole, so a
    rubric keyword "parking spot" can match a class named `ParkingSpot`.
    """
    raw: list[str] = []
    buf = ""
    for ch in text:
        if ch.isalnum():
            buf += ch
        else:
            if buf:
                raw.append(buf)
                buf = ""
    if buf:
        raw.append(buf)

    # Case must survive until after the CamelCase split, or the split has
    # nothing to key on and "PricingStrategy" never matches "pricing strategy".
    # Keep consecutive capitals together: APIKey becomes "api", "key", not
    # "a", "p", "i", "key".
    out = {token.lower() for token in raw}
    for token in raw:
        parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", token)
        out.update(part.lower() for part in parts)
    return out


@dataclass
class TextSubmission(Submission):
    """A free-form design note. Accepted, but the weakest signal."""

    kind: ClassVar[str] = "text"
    text: str = ""

    def render_for_evaluation(self) -> str:
        return self.text

    def symbols(self) -> set[str]:
        return split_words(self.text)

    def to_payload(self) -> dict[str, Any]:
        return {"text": self.text}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TextSubmission:
        return cls(text=payload.get("text", ""))


@dataclass
class ClassSpec:
    name: str
    responsibility: str = ""
    methods: tuple[str, ...] = ()
    collaborators: tuple[str, ...] = ()


@dataclass
class DesignSubmission(Submission):
    """The primary format: named classes, responsibilities, collaborators.

    This is the format the product pushes learners towards. It is the only one
    where "did you put this behaviour in the right place" is answerable
    without guessing at prose.
    """

    kind: ClassVar[str] = "design"
    classes: list[ClassSpec] = field(default_factory=list)
    trade_offs: str = ""
    notes: str = ""

    def render_for_evaluation(self) -> str:
        lines: list[str] = []
        for c in self.classes:
            lines.append("class " + c.name)
            if c.responsibility:
                lines.append("  responsibility: " + c.responsibility)
            if c.methods:
                lines.append("  methods: " + ", ".join(c.methods))
            if c.collaborators:
                lines.append("  collaborates with: " + ", ".join(c.collaborators))
        if self.trade_offs:
            lines.append("\nTrade-offs the learner states:\n" + self.trade_offs)
        if self.notes:
            lines.append("\nNotes:\n" + self.notes)
        return "\n".join(lines)

    def symbols(self) -> set[str]:
        return split_words(self.render_for_evaluation())

    def declared_types(self) -> set[str]:
        """Class names, plus the collaborators those classes name.

        A collaborator counts: naming `PricingStrategy` as a collaborator is
        still asserting the type exists in your model, even if you did not
        write its row out. Method names and responsibility prose do not count,
        which is the whole point.
        """
        names = [c.name for c in self.classes]
        names += [collab for c in self.classes for collab in c.collaborators]
        return split_words(" ".join(names))

    def validate(self) -> None:
        if not self.classes:
            raise InvalidSubmission("A design submission needs at least one class.")
        if any(not c.name.strip() for c in self.classes):
            raise InvalidSubmission("Every class needs a name.")
        missing = sorted(c.name for c in self.classes if not c.responsibility.strip())
        if missing:
            raise InvalidSubmission(
                "State a responsibility for each class. Missing: " + ", ".join(missing)
            )
        super().validate()

    def to_payload(self) -> dict[str, Any]:
        return {
            "classes": [
                {
                    "name": c.name,
                    "responsibility": c.responsibility,
                    "methods": list(c.methods),
                    "collaborators": list(c.collaborators),
                }
                for c in self.classes
            ],
            "trade_offs": self.trade_offs,
            "notes": self.notes,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> DesignSubmission:
        return cls(
            classes=[
                ClassSpec(
                    name=c.get("name", ""),
                    responsibility=c.get("responsibility", ""),
                    methods=tuple(c.get("methods", ())),
                    collaborators=tuple(c.get("collaborators", ())),
                )
                for c in payload.get("classes", [])
            ],
            trade_offs=payload.get("trade_offs", ""),
            notes=payload.get("notes", ""),
        )


@dataclass
class CodeSubmission(Submission):
    """Python source. Parsed with `ast`, so the symbols are real, not guessed.

    If the code does not parse we keep the submission and fall back to word
    matching, and the evaluator says so. A syntax error should cost the learner
    accuracy of feedback, not the whole attempt.
    """

    kind: ClassVar[str] = "code"
    source: str = ""
    language: str = "python"

    def render_for_evaluation(self) -> str:
        return self.source

    def parse_error(self) -> str | None:
        if self.language != "python":
            return None
        try:
            ast.parse(self.source)
        except SyntaxError as exc:
            return "line {}: {}".format(exc.lineno, exc.msg)
        return None

    def symbols(self) -> set[str]:
        if self.language != "python":
            return split_words(self.source)
        try:
            tree = ast.parse(self.source)
        except SyntaxError:
            return split_words(self.source)
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
            elif isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.append(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.append(node.value)
        return split_words(" ".join(names))

    def declared_types(self) -> set[str]:
        """Names of classes actually defined, plus the base classes they name."""
        if self.language != "python":
            return self.symbols()
        try:
            tree = ast.parse(self.source)
        except SyntaxError:
            return self.symbols()
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.append(node.name)
                names += [b.id for b in node.bases if isinstance(b, ast.Name)]
        return split_words(" ".join(names))

    def to_payload(self) -> dict[str, Any]:
        return {"source": self.source, "language": self.language}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CodeSubmission:
        return cls(
            source=payload.get("source", ""),
            language=payload.get("language", "python"),
        )
