"""Domain-level errors.

These are raised by the domain and translated to HTTP status codes at the
web edge. Nothing in the domain knows about HTTP.
"""


class DomainError(Exception):
    """Base class for every error the domain raises deliberately."""


class NotFound(DomainError):
    """A referenced aggregate does not exist."""


class IllegalTransition(DomainError):
    """An attempt was asked to move to a state it cannot reach from here."""


class InvalidSubmission(DomainError):
    """A submission cannot be accepted for evaluation as written."""
