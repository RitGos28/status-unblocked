"""Domain-level errors. Mapped to RFC-9457 problem+json responses in the API layer."""


class StandupError(Exception):
    """Base for every error this application raises deliberately."""

    status_code = 500
    title = "Internal error"


class UnauthorizedError(StandupError):
    """No signed-in member. Browsers get a page explaining how to sign in."""

    status_code = 401
    title = "Sign in with your team code"


class ManagerUnauthorizedError(UnauthorizedError):
    """No manager signed in. The portal has its own username and password."""

    status_code = 401
    title = "Sign in to the manager portal"


class NotFoundError(StandupError):
    status_code = 404
    title = "Not found"


class BadRequestError(StandupError):
    """The request's own content is wrong: an empty name, an unknown time zone."""

    status_code = 400
    title = "Invalid input"


class ValidationFailure(StandupError):
    """Raised when a digest fails faithfulness validation under strict mode."""

    status_code = 422
    title = "Digest failed faithfulness validation"


class ConfigurationError(StandupError):
    """A required setting is missing for the operation being attempted."""

    status_code = 500
    title = "Configuration error"


class SpanDriftError(StandupError):
    """A computed span does not match its text. A bug, never user error."""

    status_code = 500
    title = "Internal error: citation offsets did not round-trip"


class EmptySubmissionError(StandupError):
    status_code = 400
    title = "Submission was empty"


class ConflictError(StandupError):
    """The request contradicts the record, e.g. rebuilding a day retention removed."""

    status_code = 409
    title = "Not possible any more"
