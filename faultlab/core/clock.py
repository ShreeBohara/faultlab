"""Wall-clock helpers. Logical time belongs to the environment kernel, never to this module."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_text() -> str:
    return utc_now().isoformat()
