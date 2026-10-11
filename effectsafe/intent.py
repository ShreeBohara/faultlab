"""Operation identity: canonical bytes, intent digests, derived keys.

The canonical form is byte-identical to the lab's (``faultlab.core.canonical``) so an intent
hash recorded by the lab equals the one the layer computes at runtime; a lab test pins them.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def canonical_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")

    def encode_nested(item):
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        raise TypeError("Canonical JSON requires JSON values or validated models")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=encode_nested)


def digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def derive_key(namespace: str, intent_hash: str, *, prefix: str = "key") -> str:
    """A deterministic idempotency key for one intent in one namespace (an episode, a workflow run).

    Same intent, same namespace, same key: a retry after a lost reply carries the key the provider
    already saw. A different payload is a different intent and gets a different key.
    """
    return f"{prefix}-{sha256(f'{namespace}:{intent_hash}'.encode('utf-8')).hexdigest()[:32]}"


class Intent(BaseModel):
    """What the agent means to do, fixed before the first dispatch."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    operation_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=120)          # the tool name
    scope: str = Field(min_length=1, max_length=256)           # the resource acted on (an order, an account)
    payload: dict[str, Any] = Field(default_factory=dict)      # the request body, before any key is attached

    @property
    def intent_hash(self) -> str:
        return digest({"action": self.action, "scope": self.scope, "payload": self.payload})

    def original_bytes(self, *, key: str | None = None, key_field: str = "idempotency_key") -> str:
        """The exact bytes a dispatch sends: the canonical payload, with the key attached where the contract says."""
        body = dict(self.payload)
        if key is not None:
            body[key_field] = key
        return canonical_json(body)
