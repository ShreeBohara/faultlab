class FaultLabError(Exception):
    """Base class for every error FaultLab raises on purpose."""


class IntegrityError(FaultLabError, ValueError):
    """Evidence is malformed, contradicts its source, or has changed since it was sealed."""
