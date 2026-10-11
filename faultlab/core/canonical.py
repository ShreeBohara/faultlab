"""Canonical JSON and content digests.

Byte-identical to the legacy lab's ``app.contracts.models.canonical_json`` and ``content_hash``
(sorted keys, no spaces, UTF-8 kept as is, NaN refused), so every identity recorded by earlier
campaigns keeps its meaning. A test pins the two implementations to each other.
"""

from hashlib import sha256
import json

from pydantic import BaseModel


def canonical_json(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")

    def encode_nested(item):
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        raise TypeError("Canonical JSON requires JSON values or validated models")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
                      default=encode_nested)


def content_hash(value) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()
