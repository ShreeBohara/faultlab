"""Explicit, opt-in connection checks; importing this package never calls providers."""


class ProviderCheckError(RuntimeError):
    """A deliberately sanitized error suitable for terminal output."""

    def __init__(self, message: str, *, response: str | None = None) -> None:
        super().__init__(message)
        self.response = response


def redact_text(text: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text
