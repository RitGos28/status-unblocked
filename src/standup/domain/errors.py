"""Domain-level errors. Mapped to RFC-9457 problem+json responses in the API layer."""


class StandupError(Exception):
    """Base for every error this application raises deliberately."""

    status_code = 500
    title = "Internal error"


class UnauthorizedError(StandupError):
    """No signed-in member. Browsers get a page explaining how to sign in."""

    status_code = 401
    title = "Sign in with your personal link"


class NotFoundError(StandupError):
    status_code = 404
    title = "Not found"


class ValidationFailure(StandupError):
    """Raised when a digest fails faithfulness validation under strict mode."""

    status_code = 422
    title = "Digest failed faithfulness validation"


class EmptySubmissionError(StandupError):
    status_code = 400
    title = "Submission was empty"
