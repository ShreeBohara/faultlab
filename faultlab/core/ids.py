"""Identifiers and digests, with the legacy lab's exact spelling rules."""

import re
from typing import Annotated
from uuid import uuid4

from pydantic import StringConstraints

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
DIGEST_PATTERN = r"^[a-f0-9]{64}$"
REF_PATTERN = r"^/"

Id = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=ID_PATTERN)]
Digest = Annotated[str, StringConstraints(pattern=DIGEST_PATTERN)]
# A JSON pointer into an envelope's source facts (RFC 6901), always absolute.
Ref = Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=REF_PATTERN)]

_ID = re.compile(ID_PATTERN)
_DIGEST = re.compile(DIGEST_PATTERN)


def new_id(prefix: str = "id") -> str:
    """``<prefix>-<32 hex>``, the shape every legacy record identifier has."""
    return f"{prefix}-{uuid4().hex}"


def is_id(value) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 128 and _ID.fullmatch(value) is not None


def is_digest(value) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None
