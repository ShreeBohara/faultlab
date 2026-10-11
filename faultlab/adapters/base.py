"""The adapter interface (plan phase 1.6): how an agent is driven through a trial session.

An adapter is reviewed code with an identity: an id, a version, the model it runs (or none), and
the digest of its own source file, so a plan can name it (``AgentManifest``) and an envelope can
record exactly what acted (``ExecutionIdentity.adapter_digest``). ``act(session)`` is the whole
contract: the adapter may call the pack's tools, wait, charge model calls and hand back one report
through the session, and nothing else. Request data never chooses an adapter; the registry does.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from pydantic import Field

from faultlab.core import Digest, StrictModel, file_digest
from faultlab.evidence.models import AgentManifest

NO_MODEL = "deterministic/none"


class AdapterSpec(StrictModel):
    adapter_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    model: str = Field(default=NO_MODEL, min_length=1, max_length=200)     # the model the adapter runs, or NO_MODEL
    packs: list[str] = Field(default_factory=list)                        # pack ids it can drive; empty means any
    settings_digest: Digest | None = None
    prompt_digest: Digest | None = None


class BaseAdapter:
    """Subclass, set ``spec`` and implement ``act``. The digest is the implementing module's file digest."""

    spec: AdapterSpec

    @property
    def adapter_id(self) -> str:
        return self.spec.adapter_id

    @property
    def version(self) -> str:
        return self.spec.version

    @property
    def digest(self) -> str:
        module = sys.modules[type(self).__module__]
        return file_digest(Path(module.__file__))

    def manifest(self) -> AgentManifest:
        """What a plan records about this adapter before admission."""
        return AgentManifest(adapter_id=self.spec.adapter_id, version=self.spec.version, model=self.spec.model,
                             settings_digest=self.spec.settings_digest, prompt_digest=self.spec.prompt_digest)

    def supports(self, pack_id: str) -> bool:
        return not self.spec.packs or pack_id in self.spec.packs

    async def act(self, session) -> Any:
        raise NotImplementedError


__all__ = ["NO_MODEL", "AdapterSpec", "BaseAdapter"]
